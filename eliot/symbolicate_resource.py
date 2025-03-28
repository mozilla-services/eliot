# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Resource implementing the Symbolication v4 and v5 APIs.

``debug_filename``
   The original filename the debug symbols are for.

   For example, ``libmozglue.dylib``.

``debug_id``
   When files are compiled, a debug id is generated. This is the debug id.

   For example, ``11FB836EE6723C07BFF775900077457B0``.

``sym_filename``
   This is the symbol filename. Generally, it's the ``debug_filename`` with ``.sym``
   appended except for ``.pdb`` files where ``.sym`` replaces ``.pdb.

   For example, ``libmozglue.dylib.sym``.

"""

from collections import Counter
import contextlib
from itertools import groupby
import json
import logging
import re
import time

import falcon

from eliot import downloader
from eliot.libmarkus import METRICS
from eliot.libsymbolic import (
    BadDebugIDError,
    bytes_to_symcache,
    get_module_filename,
    parse_sym_file,
    ParseSymFileError,
    symcache_to_bytes,
)


LOGGER = logging.getLogger(__name__)


class DebugStats:
    """Class for keeping track of metrics and such."""

    def __init__(self):
        self.data = {}

    def _setvalue(self, data, key, value):
        ptr = data
        if isinstance(key, str):
            parts = key.split(".")
        else:
            parts = key
        for part in parts[:-1]:
            if part not in ptr:
                ptr[part] = {}
            ptr = ptr[part]

        ptr[parts[-1]] = value

    def _getvalue(self, data, key, default=None):
        ptr = data
        if isinstance(key, str):
            parts = key.split(".")
        else:
            parts = key
        for part in parts:
            if part not in ptr:
                return default
            ptr = ptr[part]
        return ptr

    def get(self, key, default=None):
        return self._getvalue(self.data, key=key, default=default)

    def set(self, key, value):
        self._setvalue(self.data, key=key, value=value)

    def incr(self, key, value=1):
        current_value = self._getvalue(self.data, key=key, default=0)
        self._setvalue(self.data, key=key, value=current_value + value)

    @contextlib.contextmanager
    def timer(self, key):
        start_time = time.perf_counter()

        yield

        end_time = time.perf_counter()
        delta = end_time - start_time
        self._setvalue(self.data, key, delta)


class InvalidModules(Exception):
    pass


class InvalidStacks(Exception):
    pass


# A valid debug id is zero or more hex characters.
VALID_DEBUG_ID = re.compile(r"^([A-Fa-f0-9]*)$")

# A valid debug filename consists of zero or more alpha-numeric characters, some
# punctuation, and spaces.
VALID_DEBUG_FILENAME = re.compile(r"^([A-Za-z0-9_.+{}@<> ~-]*)$")

# Maximum number of symbolication jobs to do in a single request
MAX_JOBS = 10


def validate_modules(modules):
    """Validate modules and raise an error if invalid

    :arg modules: list of ``[debug_filename, debug_id]`` lists where the debug_id is
        effectively hex and the debug_filename is a library name.

    :raises InvalidModules: if there's a validation problem with the modules

    """
    if not isinstance(modules, list):
        raise InvalidModules("modules must be a list")

    for i, item in enumerate(modules):
        if not isinstance(item, list) or len(item) != 2:
            LOGGER.debug("invalid module %r", item)
            raise InvalidModules(
                f"module index {i} does not have a debug_filename and debug_id"
            )

        debug_filename, debug_id = modules[i]
        if not isinstance(debug_filename, str) or not VALID_DEBUG_FILENAME.match(
            debug_filename
        ):
            LOGGER.debug("invalid debug_filename %r", modules[i])
            raise InvalidModules(f"module index {i} has an invalid debug_filename")

        if not isinstance(debug_id, str) or not VALID_DEBUG_ID.match(debug_id):
            LOGGER.debug("invalid debug_id %r", modules[i])
            raise InvalidModules(f"module index {i} has an invalid debug_id")


def validate_stacks(stacks, modules):
    """Stacks is a list of (module index, module offset) integers

    :arg stacks: the stacks that came in the request

    :arg modules: the modules that came in the request

    :raises InvalidStacks: if there's a validation problem with the stacks

    """
    if not isinstance(stacks, list):
        raise InvalidStacks("stacks must be a list of lists")

    if len(stacks) == 0:
        raise InvalidStacks("no stacks specified")

    for i, stack in enumerate(stacks):
        if not isinstance(stack, list):
            LOGGER.debug("invalid stack %r", stack)
            raise InvalidStacks(f"stack {i} is not a list")

        for frame_i, frame in enumerate(stack):
            if not isinstance(frame, list) or len(frame) != 2:
                LOGGER.debug("invalid frame %r", frame)
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} is not a list of two items"
                )

            module_index, module_offset = frame
            if not isinstance(module_index, int):
                LOGGER.debug("invalid module_index %r", frame)
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} has an invalid module_index"
                )
            # The module_index is -1 if the memory address isn't in a module and
            # it's an offset in the binary
            if not -1 <= module_index < len(modules):
                LOGGER.debug("invalid module_index %r", frame)
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} has a module_index that isn't in modules"
                )

            if not isinstance(module_offset, int) or module_offset < -1:
                LOGGER.debug("invalid module_offset %r", frame)
                raise InvalidStacks(
                    f"stack {i} frame {frame_i} has an invalid module_offset"
                )


class SymbolicateBase:
    def __init__(self, downloader, cache, tmpdir):
        self.downloader = downloader
        self.cache = cache
        self.tmpdir = tmpdir

    def download_sym_file(self, debug_filename, debug_id):
        """Download a symbol file.

        :arg debug_filename: the debug filename
        :arg debug_id: the debug id

        :returns: sym file as bytes or None

        """
        if debug_filename.endswith(".pdb"):
            sym_filename = debug_filename[:-4] + ".sym"
        else:
            sym_filename = debug_filename + ".sym"

        try:
            data = self.downloader.get(debug_filename, debug_id, sym_filename)

        except downloader.FileNotFound:
            return None

        except downloader.ErrorFileNotFound:
            # FIXME(willkg): We probably want to handle this case differently and maybe
            # raise a HTTP 500 because the symbolication request can't be fulfilled.
            # The downloader will capture these issues and at some point, we'll feel
            # stable and can switch this then.
            return None

        return data

    @METRICS.timer_decorator("symbolicate.parse_sym_file.parse")
    def parse_sym_file(self, debug_filename, debug_id, data):
        """Convert sym file to symcache file

        :arg debug_filename: the debug filename
        :arg debug_id: the debug id
        :arg data: bytes

        :returns: symcache or None

        """
        try:
            return parse_sym_file(debug_filename, debug_id, data)

        except BadDebugIDError:
            # If the debug id isn't valid, then there's nothing to parse, so
            # log something, emit a metric, and move on
            LOGGER.exception("debug_id parse error: %r", debug_id)
            METRICS.incr(
                "symbolicate.parse_sym_file.error", tags=["reason:bad_debug_id"]
            )

        except ParseSymFileError as psfe:
            LOGGER.exception("sym file parse error: %r %r", debug_filename, debug_id)
            METRICS.incr(
                "symbolicate.parse_sym_file.error",
                tags=[f"reason:{psfe.reason_code}"],
            )

    def get_symcache(self, debug_filename, debug_id, debug_stats):
        """Gets the symcache for a given module.

        This uses the cachemanager and downloader to get the symcache.

        :arg debug_filename: the debug filename
        :arg debug_id: the debug id
        :arg debug_stats: DebugStats instance for keeping track of timings and other
            useful things

        :returns: ``(symcache, filename)`` or ``None``

        """
        if not debug_filename or not debug_id:
            # If we don't have a debug_filename or debug_id, there's nothing we can
            # download, so return None
            return

        symcache = None
        module_filename = None

        # Get the symcache from cache if it's there
        start_time = time.perf_counter()
        debug_stats.incr("cache_lookups.count", 1)

        cache_key = "%s/%s.symc" % (
            debug_filename.replace("/", ""),
            debug_id.upper().replace("/", ""),
        )

        try:
            # Pull the symcache file from cache if we can
            data = self.cache.get(cache_key)
            symcache = bytes_to_symcache(data["symcache"])
            module_filename = data["filename"]
            debug_stats.incr("cache_lookups.hits", 1)
        except KeyError:
            debug_stats.incr("cache_lookups.hits", 0)

        end_time = time.perf_counter()
        debug_stats.incr("cache_lookups.time", end_time - start_time)

        if symcache:
            return symcache, module_filename

        # We didn't find it in the cache, so try to download it
        download_start_time = time.perf_counter()
        sym_file = self.download_sym_file(debug_filename, debug_id)
        download_end_time = time.perf_counter()

        debug_stats.incr("downloads.count", 1)

        if sym_file is None:
            # Nothing was downloaded, so capture the timing as a download fail and
            # return None
            debug_stats.incr(
                [
                    "downloads",
                    "fail_time_per_module",
                    f"{debug_filename}/{debug_id}",
                ],
                download_end_time - download_start_time,
            )
            return

        debug_stats.incr(
            [
                "downloads",
                "size_per_module",
                f"{debug_filename}/{debug_id}",
            ],
            len(sym_file),
        )
        debug_stats.incr(
            [
                "downloads",
                "time_per_module",
                f"{debug_filename}/{debug_id}",
            ],
            download_end_time - download_start_time,
        )

        # Extract the module filename--this is either debug_filename or
        # pe_filename on Windows
        module_filename = get_module_filename(sym_file, debug_filename)

        # Parse the SYM file into a symcache
        parse_start_time = time.perf_counter()
        symcache = self.parse_sym_file(debug_filename, debug_id, sym_file)
        parse_end_time = time.perf_counter()

        if symcache is None:
            # The sym file we downloaded isn't valid, so capture timings and return None
            debug_stats.incr(
                [
                    "parse_sym",
                    "fail_time_per_module",
                    f"{debug_filename}/{debug_id}",
                ],
                parse_end_time - parse_start_time,
            )
            return

        debug_stats.incr(
            [
                "parse_sym",
                "time_per_module",
                f"{debug_filename}/{debug_id}",
            ],
            parse_end_time - parse_start_time,
        )

        # If we have a valid symcache file, cache it to disk, capture some debug stats,
        # and then return it
        save_start_time = time.perf_counter()
        data = symcache_to_bytes(symcache)
        save_end_time = time.perf_counter()

        data = {"symcache": data, "filename": module_filename}
        self.cache.set(cache_key, data)

        debug_stats.incr(
            [
                "save_symcache",
                "time_per_module",
                f"{debug_filename}/{debug_id}",
            ],
            save_end_time - save_start_time,
        )

        return symcache, module_filename

    def symbolicate(self, jobs, debug_stats):
        """Takes jobs and returns symbolicated results.

        :arg jobs: list of jobs containing stack and module information
        :arg debug_stats: DebugStats instance for keeping track of timings and other
            useful things

        :returns: list of result dicts with "stacks" and "found_modules" keys per the
            symbolication v5 response

        """

        # List of:
        #
        # ((debug_filename, debug_id), frame_info)
        #
        # tuples
        frames = []

        job_results = []

        # Go through jobs, stacks, and frames and build a list of all the things to
        # symbolicate
        for job in jobs:
            # List of stacks
            stacks = job["stacks"]

            # List of [debug_filename, debug_id] lists
            memorymap = job["memoryMap"]

            stacks_results = []
            for stack in stacks:
                stack_results = []
                for frame_i, frame in enumerate(stack):
                    module_index, module_offset = frame

                    if 0 <= module_index < len(memorymap):
                        debug_filename, debug_id = memorymap[module_index]
                    else:
                        debug_filename = ""
                        debug_id = ""

                    frame_info = {
                        "frame": frame_i,
                        "module": debug_filename or "<unknown>",
                        "module_offset": hex(module_offset),
                    }

                    stack_results.append(frame_info)
                    frames.append(
                        (
                            # module information
                            (debug_filename, debug_id),
                            # frame information--since this is a mutable structure, when
                            # we update it here, we're updating it in job_results as
                            # well
                            frame_info,
                        )
                    )
                stacks_results.append(stack_results)

            job_results.append(
                {
                    "stacks": stacks_results,
                    "found_modules": None,
                }
            )

        # Map of (debug_filename, debug_id) -> lookup result
        module_lookup = {}

        # Sort all the frames to symbolicate by module info. Then iterate
        # module-by-module through all the frames to symbolicate and lookup symbols for
        # them
        frames.sort(key=lambda frame: frame[0])

        for module_info, frames_group in groupby(frames, key=lambda frame: frame[0]):
            debug_filename, debug_id = module_info
            if not debug_filename or not debug_id:
                continue

            ret = self.get_symcache(debug_filename, debug_id, debug_stats)
            if ret is None:
                module_lookup[(debug_filename, debug_id)] = False
                continue

            module_lookup[(debug_filename, debug_id)] = True
            symcache, module_filename = ret

            for _, frame_info in frames_group:
                module_offset = int(frame_info["module_offset"], 16)

                frame_info["module"] = module_filename

                if module_offset < 0:
                    continue

                sourceloc_list = symcache.lookup(module_offset)
                if not sourceloc_list:
                    continue

                # sourceloc_list can have multiple entries: It starts with the innermost
                # inline stack frame, and then advances to its caller, and then its
                # caller, and so on, until it gets to the outer function.
                # We process the outer function first, and then add inline stack frames
                # afterwards. The outer function is the last item in sourceloc_list.
                sourceloc = sourceloc_list[-1]

                frame_info["function"] = sourceloc.symbol
                frame_info["function_offset"] = hex(module_offset - sourceloc.sym_addr)
                if sourceloc.full_path:
                    frame_info["file"] = sourceloc.full_path

                # Only add a "line" if it's non-zero and not None, and if there's a
                # file--otherwise the line doesn't mean anything
                if sourceloc.line and frame_info.get("file"):
                    frame_info["line"] = sourceloc.line

                if len(sourceloc_list) > 1:
                    # We have inline information. Add an "inlines" property with a list
                    # of { function, file, line } entries.
                    inlines = []
                    for inline_sourceloc in sourceloc_list[:-1]:
                        inline_data = {
                            "function": inline_sourceloc.symbol,
                        }

                        if inline_sourceloc.full_path:
                            inline_data["file"] = inline_sourceloc.full_path

                        if inline_sourceloc.line and inline_data.get("file"):
                            inline_data["line"] = inline_sourceloc.line

                        inlines.append(inline_data)

                    frame_info["inlines"] = inlines

        # Update found_modules in the results
        for job_index, job_result in enumerate(job_results):
            # Convert modules to a map of debug_filename/debug_id -> True/False/None on
            # whether we found the sym file (True), didn't find it (False), or never
            # looked for it (None)
            found_modules = {
                f"{debug_filename}/{debug_id}": module_lookup.get(
                    (debug_filename, debug_id)
                )
                for debug_filename, debug_id in jobs[job_index]["memoryMap"]
            }

            job_result["found_modules"] = found_modules

        # Total number of frames we symbolicated in this request
        METRICS.histogram("symbolicate.frames_count", value=len(frames))

        return job_results


def _load_payload(req):
    try:
        return json.load(req.bounded_stream)
    except json.JSONDecodeError as exc:
        METRICS.incr("symbolicate.request_error", tags=["reason:bad_json"])
        raise falcon.HTTPBadRequest(title="Payload is not valid JSON") from exc


def _validate_and_measure_jobs(jobs, api_version):
    for i, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise falcon.HTTPBadRequest(title=f"job {i} is invalid")
        if "stacks" not in job:
            raise falcon.HTTPBadRequest(
                title=f"job {i} is invalid: no stacks specified"
            )
        if "memoryMap" not in job:
            raise falcon.HTTPBadRequest(
                title=f"job {i} is invalid: no memoryMap specified"
            )

        stacks = job["stacks"]
        modules = job["memoryMap"]

        try:
            validate_modules(modules)
        except InvalidModules as exc:
            METRICS.incr("symbolicate.request_error", tags=["reason:invalid_modules"])
            # NOTE(willkg): the str of an exception is the message; we need to
            # control the message carefully so we're not spitting unsanitized data
            # back to the user in the error
            raise falcon.HTTPBadRequest(
                title=f"job {i} has invalid modules: {exc}"
            ) from exc

        try:
            validate_stacks(stacks, modules)
        except InvalidStacks as exc:
            METRICS.incr("symbolicate.request_error", tags=["reason:invalid_stacks"])
            # NOTE(willkg): the str of an exception is the message; we need to
            # control the message carefully so we're not spitting unsanitized data
            # back to the user in the error
            raise falcon.HTTPBadRequest(
                title=f"job {i} has invalid stacks: {exc}"
            ) from exc

        METRICS.histogram(
            "symbolicate.stacks_count",
            value=len(stacks),
            tags=[f"version:{api_version}"],
        )


# NOTE(Willkg): This API endpoint version is deprecated. We shouldn't add new features
# or fix bugs with it.
class SymbolicateV4(SymbolicateBase):
    @METRICS.timer_decorator("symbolicate.api", tags=["version:v4"])
    def on_post(self, req, resp):
        METRICS.incr("pageview", tags=["path:/symbolicate/v4", "method:post"])

        # NOTE(willkg): we define this and pass it around, but don't return it in the
        # results because this API is deprecated
        debug_stats = DebugStats()

        payload = _load_payload(req)

        # Convert to a list of jobs, validate and measure the jobs, symbolicate and then
        # unwrap that to a single symdata result
        jobs = [payload]
        _validate_and_measure_jobs(jobs, api_version="v4")
        symdata = self.symbolicate(jobs, debug_stats)[0]

        # Convert the symbolicate output to symbolicate/v4 output
        def frame_to_function(frame):
            if "function" not in frame:
                try:
                    function = hex(frame["module_offset"])
                except TypeError:
                    # Happens if 'module_offset' is not an int16 and thus can't be
                    # represented in hex.
                    function = str(frame["module_offset"])
            else:
                function = frame["function"]
            return f"{function} (in {frame['module']})"

        symbolicated_stacks = [
            [frame_to_function(frame) for frame in stack] for stack in symdata["stacks"]
        ]
        known_modules = [
            symdata["found_modules"].get(f"{debug_filename}/{debug_id}", None)
            for debug_filename, debug_id in payload["memoryMap"]
        ]

        results = {
            "symbolicatedStacks": symbolicated_stacks,
            "knownModules": known_modules,
        }
        resp.text = json.dumps(results)


class SymbolicateV5(SymbolicateBase):
    @METRICS.timer_decorator("symbolicate.api", tags=["version:v5"])
    def on_post(self, req, resp):
        METRICS.incr("pageview", tags=["path:/symbolicate/v5", "method:post"])

        payload = _load_payload(req)

        is_debug = req.get_header("Debug", default=False)

        if "jobs" in payload:
            jobs = payload["jobs"]
        else:
            jobs = [payload]

        if len(jobs) > MAX_JOBS:
            METRICS.incr("symbolicate.request_error", tags=["reason:too_many_jobs"])
            raise falcon.HTTPBadRequest(
                title=f"please limit number of jobs in a single request to <= {MAX_JOBS}"
            )

        METRICS.histogram(
            "symbolicate.jobs_count", value=len(jobs), tags=["version:v5"]
        )
        LOGGER.debug(f"Number of jobs: {len(jobs)}")

        debug_stats = DebugStats()

        # Validate, measure, and symbolicate jobs
        with debug_stats.timer("time"):
            _validate_and_measure_jobs(jobs, api_version="v5")
            results = self.symbolicate(jobs, debug_stats)
        response = {"results": results}

        # Add debug information to response if requested
        if is_debug:
            # Calculate modules
            all_modules = Counter()
            for result in results:
                all_modules.update(
                    [
                        key
                        for key, val in result["found_modules"].items()
                        if val is not None
                    ]
                )
            debug_stats.set("modules.count", value=sum(all_modules.values()))
            for key, count in all_modules.items():
                debug_stats.set(["modules", "stacks_per_module", key], count)

            # Calculate aggregates
            debug_stats.set(
                ["downloads", "size"],
                sum(
                    [0]
                    + list(
                        debug_stats.get(
                            ["downloads", "size_per_module"], default={}
                        ).values()
                    )
                ),
            )
            debug_stats.set(
                ["downloads", "time"],
                sum(
                    [0]
                    + list(
                        debug_stats.get(
                            ["downloads", "time_per_module"], default={}
                        ).values()
                    )
                ),
            )
            debug_stats.set(
                ["parse_sym", "time"],
                sum(
                    [0]
                    + list(
                        debug_stats.get(
                            ["parse_sym", "time_per_module"], default={}
                        ).values()
                    )
                ),
            )
            debug_stats.set(
                ["save_symcache", "time"],
                sum(
                    [0]
                    + list(
                        debug_stats.get(
                            ["save_symcache", "time_per_module"], default={}
                        ).values()
                    )
                ),
            )

            # Set values to 0 if they're missing by incrementing them by 0
            debug_stats.incr("cache_lookups.count", 0)
            debug_stats.incr("cache_lookups.time", 0.0)
            debug_stats.incr("downloads.count", 0)

            # Add debug stats to response
            response["debug"] = debug_stats.data

        num_jobs = len(jobs)
        num_symbols = sum(
            [sum([len(stack) for stack in job["stacks"]]) for job in jobs]
        )
        LOGGER.info(
            "symbolicate/v5: jobs: %s, symbols: %s, time: %s",
            num_jobs,
            num_symbols,
            debug_stats.get("time"),
        )
        resp.text = json.dumps(response)
