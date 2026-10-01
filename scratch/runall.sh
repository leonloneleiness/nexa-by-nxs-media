export PYTHONIOENCODING=utf-8
while IFS='|' read -r cat params; do
  [ -z "$cat" ] && continue
  PYTHONPATH=. .venv/Scripts/python scratch/ev.py "$cat" "$params" | grep -v "^  ok"
done < "$1"
