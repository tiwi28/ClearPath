const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const { JSDOM } = require('jsdom')

test('Fast Refresh waits for replacement map sources and restores current data', async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>')
  global.window = dom.window
  global.document = dom.window.document
  Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true })
  global.IS_REACT_ACT_ENVIRONMENT = true

  const refresh = await import('../node_modules/@vitejs/plugin-react/dist/refresh-runtime.js')
  refresh.injectIntoGlobalHook(global)
  const React = require('react')
  const { createRoot } = require('react-dom/client')
  const ts = require('typescript')
  const maps = []

  class MapMock {
    constructor() { this.handlers = {}; this.sources = {}; maps.push(this) }
    addControl() {}
    on(name, callback) { this.handlers[name] = callback }
    addSource(name) { this.sources[name] = { setData(data) { this.data = data } } }
    addLayer() {}
    setLayoutProperty() {}
    getCanvas() { return { style: {} } }
    getSource(name) { return this.sources[name] }
    getBounds() {
      return { getWest: () => -79.4, getEast: () => -79.3, getSouth: () => 43.6, getNorth: () => 43.7 }
    }
    remove() {}
    fitBounds() {}
  }
  const maplibre = {
    Map: MapMock, NavigationControl: class {}, setWorkerUrl() {},
    LngLatBounds: class { extend() { return this } },
  }
  const mapData = (() => {
    const module = { exports: {} }
    const source = ts.transpileModule(fs.readFileSync('./src/mapData.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
    vm.runInThisContext(`(function(require,module,exports){${source}
})`)(require, module, module.exports)
    return module.exports
  })()
  const compiled = ts.transpileModule(fs.readFileSync('./src/components/MapView.tsx', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText
  function evaluateComponent() {
    const module = { exports: {} }
    const requireDependency = (name) => name === 'maplibre-gl' ? maplibre
      : name === '../format' ? { RISK_STOPS: [[0, '#fff'], [1, '#000']] }
      : name === '../mapData' ? mapData
      : name.endsWith('?worker&url') ? { default: 'worker.mjs' }
        : name.endsWith('.css') ? {} : require(name)
    vm.runInThisContext(`(function(require,module,exports){${compiled}\n})`)(requireDependency, module, module.exports)
    return module.exports
  }

  const previous = evaluateComponent()
  refresh.registerExportsForReactRefresh('MapView', previous)
  const root = createRoot(document.getElementById('root'))
  const props = {
    barriers: { type: 'FeatureCollection', features: [{
      type: 'Feature', geometry: { type: 'Point', coordinates: [-79.3823, 43.6547] },
      properties: { id: 1, source: '311' },
    }] },
    plan: { ideal: null, transit: [], accessible: { geometry: { type: 'LineString', coordinates: [[-79.3832, 43.6534], [-79.3802, 43.6561]] }, unverified: [] } },
    start: null, destination: null, onViewport() {}, onPoint() {},
  }
  try {
    await React.act(async () => root.render(React.createElement(previous.default, props)))
    await React.act(async () => maps[0].handlers.load())
    const next = evaluateComponent()
    refresh.registerExportsForReactRefresh('MapView', next)
    await React.act(async () => {
      refresh.validateRefreshBoundaryAndEnqueueUpdate('MapView', previous, next)
      await new Promise((resolve) => setTimeout(resolve, 40))
    })
    assert.equal(maps.length, 2)
    assert.equal(maps[1].getSource('barriers'), undefined)
    await React.act(async () => maps[1].handlers.load())
    assert.deepEqual(maps[1].getSource('barriers').data.features, props.barriers.features)
    assert.deepEqual(maps[1].getSource('route').data.features[0].geometry, props.plan.accessible.geometry)
  } finally {
    await React.act(async () => root.unmount())
    dom.window.close()
  }
})
