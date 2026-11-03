import json, sys
from pathlib import Path
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

BASE = "https://developer.microsoft.com/json-schemas/fabric/"
# Local clone of https://github.com/microsoft/json-schemas (fabric folder).
# Usage: python validate.py <report-folder> [path-to-json-schemas/fabric]
ROOT = Path(sys.argv[2] if len(sys.argv) > 2 else "json-schemas/fabric")

def retrieve(uri):
    if uri.startswith(BASE):
        p = ROOT / uri[len(BASE):].split("#")[0]
        return Resource.from_contents(json.loads(p.read_text()), default_specification=DRAFT7)
    raise LookupError(uri)

registry = Registry(retrieve=retrieve)
errors = 0; checked = 0
for f in sorted(Path(sys.argv[1]).rglob("*")):
    if f.suffix not in (".json", ".pbir", ".pbip", ".pbism") and f.name != ".platform":
        continue
    doc = json.loads(f.read_text())
    sch = doc.get("$schema")
    if not sch or not sch.startswith(BASE):
        continue
    schema = retrieve(sch).contents
    v = Draft7Validator(schema, registry=registry)
    errs = list(v.iter_errors(doc))
    checked += 1
    for e in errs[:5]:
        errors += 1
        print(f"{f.relative_to(sys.argv[1])}: {'/'.join(map(str, e.absolute_path))}: {e.message[:300]}")
print(f"checked {checked} files, {errors} errors")
