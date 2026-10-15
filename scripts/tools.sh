#!/usr/bin/env bash
set -euo pipefail
# Explicitly supported reference platform; no system files or global PATH edits.
test "$(uname -s)/$(uname -m)" = 'Linux/x86_64' || { echo 'Reference setup requires Linux/amd64'; exit 1; }
mkdir -p .local/bin
curl -fsSL https://kind.sigs.k8s.io/dl/v0.33.0/kind-linux-amd64 -o .local/bin/kind
curl -fsSL https://dl.k8s.io/release/v1.37.1/bin/linux/amd64/kubectl -o .local/bin/kubectl
curl -fsSL https://get.helm.sh/helm-v4.3.1-linux-amd64.tar.gz -o .local/helm.tar.gz
echo 'aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d  .local/bin/kind' | sha256sum -c -
echo '65691ff77eb6fa44c908b77a1082c9f092c3b9733b5cefabec0d1104890e21a8  .local/bin/kubectl' | sha256sum -c -
echo '0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b  .local/helm.tar.gz' | sha256sum -c -
tar -xzf .local/helm.tar.gz -C .local linux-amd64/helm
cp .local/linux-amd64/helm .local/bin/helm
chmod +x .local/bin/{kind,kubectl,helm}
echo 'Tools saved in .local/bin. Run: export PATH="$PWD/.local/bin:$PATH"'
