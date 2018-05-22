import React from 'react'
import { Loading } from './Common'
import store from './Store'

class Symbolication extends React.PureComponent {
  pageTitle = 'Symbolication'
  componentDidMount() {
    document.title = this.pageTitle
  }
  render() {
    return (
      <div className="content">
        <h1 className="title">{this.pageTitle}</h1>
        <p>
          Symbolication is when you send names of symbol file and stacks that
          refer to addresses. What you get back is the stack addresses converted
          to information from within the symbol file. In particular you get the
          code signature at that address.
        </p>
        <p>
          Symbolication is best done with tooling such as <code>curl</code>
          or Python <code>requests.post(…)</code>. This application here is to
          help you understand the API and sample it.
        </p>
        <Form />
      </div>
    )
  }
}

export default Symbolication

class Form extends React.PureComponent {
  state = {
    loading: false,
    jobs: [],
    result: null,
    jobInputs: 1,
    jsonBody: null,
    validationError: null
  }

  submit = event => {
    event.preventDefault()
    if (!this.state.jobs.length) {
      alert('No jobs yet.')
    } else {
      const jsonBody = JSON.stringify({ jobs: this.state.jobs })
      this.setState({
        loading: true,
        jsonBody,
        result: null,
        validationError: null
      })
      return fetch('/symbolicate/v5', {
        method: 'POST',
        body: jsonBody,
        headers: new Headers({
          'Content-Type': 'application/json'
        })
      }).then(r => {
        if (r.status === 200) {
          this.setState({ loading: false, validationError: null })
          r.json().then(response => {
            this.setState({ result: response }, () => {
              const el = document.querySelector('div.showresult')
              if (el) {
                el.scrollIntoView()
              }
              if (store.fetchError) {
                store.fetchError = null
              }
            })
          })
        } else if (r.status === 400) {
          r.json().then(data => {
            this.setState(
              { validationError: data.error, loading: false },
              () => {
                const el = document.querySelector('div.validationerror')
                if (el) {
                  el.scrollIntoView()
                }
                if (store.fetchError) {
                  store.fetchError = null
                }
              }
            )
          })
        } else {
          this.setState({ loading: false, validationError: null })
          store.fetchError = r
        }
      })
    }
  }

  updateJob = (index, memoryMaps, stacks) => {
    const jobs = [...this.state.jobs]
    const maps = memoryMaps.map(mm => mm.split(/\//))
    jobs[index] = { memoryMap: maps, stacks: [stacks] }
    this.setState({ jobs: jobs })
  }

  clear = event => {
    console.error('Not implemented yet')
  }

  render() {
    return (
      <div>
        {Array(this.state.jobInputs)
          .fill()
          .map((_, i) => {
            return (
              <JobForm
                key={i}
                updateJob={(mm, stacks) => this.updateJob(i, mm, stacks)}
              />
            )
          })}
        <div className="field is-grouped is-grouped-centered">
          <p className="control">
            <button className="button is-primary" onClick={this.submit}>
              Symbolicate!
            </button>
          </p>
          <p className="control">
            <button
              type="button"
              className="button is-light"
              onClick={this.clear}
            >
              Clear
            </button>
          </p>
        </div>
        {this.state.loading ? <Loading /> : null}
        {this.state.jsonBody ? (
          <PreviewJSONBody json={this.state.jsonBody} />
        ) : null}
        {this.state.validationError ? (
          <ShowValidationError error={this.state.validationError} />
        ) : null}
        {this.state.result ? <ShowResult result={this.state.result} /> : null}
        {this.state.result && this.state.jsonBody ? (
          <ShowCurl json={this.state.jsonBody} />
        ) : null}
      </div>
    )
  }
}

class PreviewJSONBody extends React.PureComponent {
  render() {
    const json = JSON.stringify(JSON.parse(this.props.json), undefined, 2)
    return (
      <div className="box">
        <h4>JSON We're Sending</h4>
        <pre>{json}</pre>
      </div>
    )
  }
}

class ShowValidationError extends React.PureComponent {
  render() {
    const { error } = this.props
    return (
      <article className="message is-danger validationerror">
        <div className="message-header">
          <p>Validation Error</p>
        </div>
        <div className="message-body">
          <code>{error}</code>
        </div>
      </article>
    )
  }
}

class ShowResult extends React.PureComponent {
  render() {
    const json = JSON.stringify(this.props.result, undefined, 2)
    return (
      <div className="box showresult">
        <h3>RESULT</h3>
        <pre>{json}</pre>
      </div>
    )
  }
}

class ShowCurl extends React.PureComponent {
  state = { copyMode: false, copied: false }
  render() {
    const { json } = this.props
    const protocol = window.location.protocol
    const hostname = window.location.host.replace(
      'localhost:3000',
      'localhost:8000'
    )
    const absoluteUrl = `${protocol}//${hostname}/symbolicate/v5`
    const command = `curl -XPOST -d '${json}' ${absoluteUrl}`
    return (
      <div className="box">
        <h3>
          <code>curl</code> Command
        </h3>
        <pre>{command}</pre>
        {this.state.copyMode ? (
          <input type="text" name="command" readOnly={true} value={command} />
        ) : null}
        <button
          type="button"
          className="button"
          onClick={event => {
            this.setState({ copyMode: true }, () => {
              const el = document.querySelector('input[name="command"]')
              el.select()
              document.execCommand('copy')
              this.setState({ copyMode: false, copied: true })
            })
          }}
        >
          Copy to clipboard
        </button>{' '}
        {this.state.copied ? <small>Copied!</small> : null}
      </div>
    )
  }
}

class JobForm extends React.PureComponent {
  state = {
    memoryMaps: [],
    stacksInputs: 1,
    invalidMemoryMaps: [],
    defaultMemoryMap: 0,
    stacks: []
  }
  componentDidMount() {
    if (this.refs.memoryMap.value) {
      this.updateMemoryMap()
    }
  }
  updateMemoryMap = () => {
    const lines = this.refs.memoryMap.value
      .trim()
      .split(/\n/g)
      .filter(line => line.trim())
      .map(line => line.trim())
    const valid = new Set()
    const invalid = new Set()
    lines.forEach(line => {
      let pathname = line
      try {
        const split = new URL(line).pathname.split(/\//g)
        pathname = [split[1], split[2]].join('/')
      } catch (_) {}
      if (pathname.split(/\//g).length === 2) {
        valid.add(pathname)
      } else {
        invalid.add(line)
      }
    })
    if (invalid.size) {
      this.setState({ invalidMemoryMaps: Array.from(invalid), memoryMaps: [] })
    } else {
      this.setState(
        { memoryMaps: Array.from(valid), invalidMemoryMaps: [] },
        () => {
          this.refs.memoryMap.value = this.state.memoryMaps.join('\n')
        }
      )
    }
  }
  render() {
    const placeholder = `
E.g. https://symbols.mozilla.org/GenerateOCSPResponse.pdb/3AACAD4A42BD449B953B5222B3CEB7233/GenerateOCSPResponse.sym
or
GenerateOCSPResponse.pdb/3AACAD4A42BD449B953B5222B3CEB7233
    `.trim()

    return (
      <div>
        <div className="field">
          <label className="label">Symbols</label>
          <div className="control">
            <textarea
              className="textarea"
              ref="memoryMap"
              placeholder={placeholder}
              defaultValue={`
                GenerateOCSPResponse.pdb/3AACAD4A42BD449B953B5222B3CEB7233
https://symbols.mozilla.org/AccessibleMarshal.pdb/3D2A1F8439554FBF8A0E0F24BEF8F0F52/AccessibleMarshal.sym

              `.trim()}
              onBlur={event => {
                this.updateMemoryMap()
              }}
            />
          </div>
          {this.state.invalidMemoryMaps.length ? (
            <p className="help is-danger">
              {this.state.invalidMemoryMaps.length} invalid lines:{' '}
              {this.state.invalidMemoryMaps.map(x => <code key={x}>{x}</code>)}
            </p>
          ) : null}
        </div>

        <label className="label">Stacks</label>
        {Array(this.state.stacksInputs)
          .fill()
          .map((_, i) => {
            return (
              <StackForm
                key={i}
                memoryMaps={this.state.memoryMaps}
                defaultMemoryMap={this.state.defaultMemoryMap}
                isNext={i === this.state.stacksInputs - 1}
                addStackInput={(address, memoryMap) => {
                  this.setState(
                    {
                      stacks: [...this.state.stacks, [memoryMap, address]],
                      stacksInputs: this.state.stacksInputs + 1,
                      defaultMemoryMap: memoryMap
                    },
                    () => {
                      this.props.updateJob(
                        this.state.memoryMaps,
                        this.state.stacks
                      )
                    }
                  )
                }}
              />
            )
          })}
      </div>
    )
  }
}

class StackForm extends React.PureComponent {
  state = {
    invalidAddress: false
  }
  add = event => {
    event.preventDefault()
    const address = parseInt(this.refs.address.value, 10)
    if (isNaN(address)) {
      this.setState({ invalidAddress: true })
    } else {
      this.setState({ invalidAddress: false }, () => {
        this.props.addStackInput(
          address,
          parseInt(this.refs.memoryMap.value, 10)
        )
      })
    }
  }
  componentDidMount() {
    if (this.props.isNext) {
      this.refs.address.focus()
    }
  }
  render() {
    return (
      <form onSubmit={this.add}>
        <div className="field has-addons has-addons-centered">
          <p className="control">
            <span className="select">
              <select
                ref="memoryMap"
                defaultValue={this.props.defaultMemoryMap}
              >
                {this.props.memoryMaps.map((memoryMap, i) => {
                  return (
                    <option value={i} key={memoryMap}>
                      {i}. {memoryMap}
                    </option>
                  )
                })}
              </select>
            </span>
          </p>
          <div className="control is-expanded">
            <input className="input" ref="address" type="text" />
            {this.state.invalidAddress ? (
              <p className="help is-danger">
                Not a valid address (must be an integer)
              </p>
            ) : null}
          </div>
          <p className="control">
            <button type="submit" className="button">
              Add
            </button>
          </p>
        </div>
      </form>
    )
  }
}