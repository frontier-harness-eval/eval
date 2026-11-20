#!/bin/bash
cat > /app/sum.sh <<'SH'
#!/bin/bash
total=0
for n in "$@"; do total=$((total + n)); done
echo "$total"
SH
chmod +x /app/sum.sh
