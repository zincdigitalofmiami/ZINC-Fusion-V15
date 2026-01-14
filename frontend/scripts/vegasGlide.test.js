const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { Module } = require('node:module')
const ts = require('typescript')

function loadTsModule(tsFilePath) {
  const source = fs.readFileSync(tsFilePath, 'utf8')
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      strict: true,
    },
    fileName: tsFilePath,
  })

  const moduleInstance = new Module(tsFilePath, module)
  moduleInstance.filename = tsFilePath
  moduleInstance.paths = Module._nodeModulePaths(path.dirname(tsFilePath))
  moduleInstance._compile(transpiled.outputText, tsFilePath)
  return moduleInstance.exports
}

const vegasGlide = loadTsModule(
  path.join(__dirname, '..', 'src', 'lib', 'vegasGlide.ts')
)

test('detectGlideFieldDrift returns no missing fields for complete rows', () => {
  const rows = [
    {
      [vegasGlide.VEGAS_GLIDE_FIELDS.restaurants.name]: 'Gordon Ramsay Pub',
      [vegasGlide.VEGAS_GLIDE_FIELDS.restaurants.casinoId]: 'casino_123',
      [vegasGlide.VEGAS_GLIDE_FIELDS.restaurants.scheduleParameters]: 'Daily',
    },
  ]

  const missing = vegasGlide.detectGlideFieldDrift(
    rows,
    vegasGlide.VEGAS_GLIDE_REQUIRED_FIELDS.restaurants
  )
  assert.deepEqual(missing, [])
})

test('assertNoGlideFieldDrift throws GlideSchemaDriftError when required fields are missing', () => {
  const rows = [
    {
      [vegasGlide.VEGAS_GLIDE_FIELDS.restaurants.casinoId]: 'casino_123',
    },
  ]

  assert.throws(
    () =>
      vegasGlide.assertNoGlideFieldDrift({
        entity: 'ops.vegas_restaurants',
        rows,
        requiredFields: vegasGlide.VEGAS_GLIDE_REQUIRED_FIELDS.restaurants,
      }),
    (err) => {
      assert.ok(err instanceof vegasGlide.GlideSchemaDriftError)
      assert.equal(err.entity, 'ops.vegas_restaurants')
      assert.ok(Array.isArray(err.missingFields))
      assert.ok(err.missingFields.length > 0)
      return true
    }
  )
})

test('assertNoGlideFieldDrift does not throw for empty result sets', () => {
  assert.doesNotThrow(() =>
    vegasGlide.assertNoGlideFieldDrift({
      entity: 'ops.vegas_restaurants',
      rows: [],
      requiredFields: vegasGlide.VEGAS_GLIDE_REQUIRED_FIELDS.restaurants,
    })
  )
})
