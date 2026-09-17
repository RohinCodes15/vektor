import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);

// Run the actual hook/component with a small hook lifecycle, without a browser dependency.
export async function mount(file, imports, name, initialProps = {}) {
  let cursor = 0;
  const slots = [];
  const effects = [];
  const cleanups = [];
  const hooks = {
    useId() { return `test-id-${cursor++}`; },
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], (value) => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useRef(value) { const index = cursor++; return slots[index] ??= { current: value }; },
    useCallback(callback, deps) { return hooks.useMemo(() => callback, deps); },
    useMemo(factory, deps) {
      const index = cursor++;
      if (!slots[index] || deps.some((value, i) => !Object.is(value, slots[index].deps[i]))) slots[index] = { deps, value: factory() };
      return slots[index].value;
    },
    useEffect(effect, deps) {
      const index = cursor++;
      if (!slots[index] || deps.some((value, i) => !Object.is(value, slots[index][i]))) {
        slots[index] = deps;
        effects.push(() => { cleanups[index]?.(); cleanups[index] = effect(); });
      }
    },
  };
  const source = await readFile(new URL(file, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  new Function("require", "exports", compiled)((id) => id === "react" ? hooks : imports[id] ?? require(id), exports);
  return {
    render(props = initialProps) { cursor = 0; return exports[name](props); },
    flush() { effects.splice(0).forEach((effect) => effect()); },
    unmount() { cleanups.forEach((cleanup) => cleanup?.()); },
  };
}

export function nodes(element) {
  if (!element || typeof element !== "object") return [];
  return [element, ...[element.props?.children].flat(Infinity).flatMap(nodes)];
}
