import sys, json; sys.path.insert(0, '.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.templates import get_template
from nexa.three_d import measure as ME
cat = sys.argv[1]
for params in json.loads(sys.argv[2]):
    sp = normalize(validate_spec({"category": cat, "params": params}))
    asm = get_template(cat)(sp)
    for c in ME.run_checks(sp, asm.parts, asm.metadata):
        print(("OK " if c.ok else "XX ") + c.name, "|", c.detail)
    print('---')
