/**
 * The frontend's dependency direction, enforced (P-DIP, P-SOC, P-COHESION).
 *
 * The layers, outermost first:
 *
 *   components / hooks   may import components, hooks, lib, store, i18n, types
 *   store                may import store, lib, i18n, types
 *   lib                  may import lib, i18n, types — never components or store
 *   i18n                 may import i18n, and types only as a type
 *   types                may import types, and i18n only as a type
 *
 * `lib` is the I/O and domain layer: `api.ts` is the only fetch, and every
 * predicate (`tweakDomain`, `tweakStatus`, `bulkStream`, `finding`) is pure. A
 * module in `lib` that needs the app's state is a store-aware service and lives
 * in `store/` instead — that is why `detection-manager`, `actionRun` and
 * `notify` moved there. Without the rule, `lib` and `store` import each other
 * and the direction means nothing.
 *
 * Tests are not analysed: they legitimately import across every layer, and
 * `src/test/` is test infrastructure, not a layer.
 */

/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment:
        "A cycle means two modules cannot be understood or tested apart. Break it by moving the shared piece down a layer.",
      from: {},
      to: { circular: true },
    },
    {
      name: "components-stay-in-their-layer",
      severity: "error",
      comment:
        "A component may compose components, hooks, lib, store, i18n and types — nothing else in src/.",
      from: { path: "^src/components/" },
      to: {
        path: "^src/",
        pathNot: "^src/(components|hooks|lib|store|i18n|types)/",
      },
    },
    {
      name: "hooks-stay-in-their-layer",
      severity: "error",
      comment:
        "A hook is glue over lib and store; it must not import a component.",
      from: { path: "^src/hooks/" },
      to: {
        path: "^src/",
        pathNot: "^src/(hooks|lib|store|i18n|types)/",
      },
    },
    {
      name: "lib-must-not-import-components",
      severity: "error",
      comment:
        "lib is the domain/I-O layer; React components sit above it, never below.",
      from: { path: "^src/lib/" },
      to: { path: "^src/components/" },
    },
    {
      name: "lib-must-not-import-store",
      severity: "error",
      comment:
        "The store depends on lib (api), so lib depending on the store at runtime is a cycle between layers. A lib module that needs app state is a store-aware service: put it in store/. A type-only import is allowed: it is erased at build, so it creates no runtime direction.",
      from: { path: "^src/lib/" },
      to: { path: "^src/store/", dependencyTypesNot: ["type-only"] },
    },
    {
      name: "store-must-not-import-components",
      severity: "error",
      comment:
        "The state layer is below the view layer; a store module that needs a component is the wrong way round.",
      from: { path: "^src/store/" },
      to: { path: "^src/components/" },
    },
    {
      name: "store-must-not-import-hooks",
      severity: "error",
      comment: "Hooks sit above the store (they read it); the store must not call back up.",
      from: { path: "^src/store/" },
      to: { path: "^src/hooks/" },
    },
    {
      name: "i18n-standalone",
      severity: "error",
      comment:
        "The i18n layer is two catalogues and a hook; it may take types (type-only) but no runtime module of the app.",
      from: { path: "^src/i18n/" },
      to: {
        path: "^src/",
        pathNot: "^src/i18n/",
        dependencyTypesNot: ["type-only"],
      },
    },
    {
      name: "types-do-not-import-runtime-code",
      severity: "error",
      comment:
        "types/ may name i18n message keys as types and nothing else; a runtime import from types would drag the UI into the data model.",
      from: { path: "^src/types/" },
      to: {
        path: "^src/",
        pathNot: "^src/(types|i18n)/",
        dependencyTypesNot: ["type-only"],
      },
    },
    {
      name: "no-dev-dependency-in-src",
      severity: "error",
      comment:
        "src/ ships to the browser: a devDependency (test tooling, linters) in a runtime module would be missing from the bundle.",
      from: { path: "^src/" },
      to: { dependencyTypes: ["npm-dev"] },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    exclude: {
      path: "(^|/)(__tests__|test)/|\\.test\\.(ts|tsx)$|\\.d\\.ts$",
    },
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default"],
    },
    reporterOptions: {
      dot: { collapsePattern: "node_modules/[^/]+" },
    },
  },
};
