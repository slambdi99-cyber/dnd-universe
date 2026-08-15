#!/usr/bin/env bash
# Give the server its own keys to reach GitHub with.
#
#   ~/dnd-universe/deploy/setup-keys.sh
#
# Two keys, not one. GitHub refuses to accept the same deploy key on two
# repositories, and these two need different access anyway:
#
#   dnd-universe  write  the site commits pages people wrote, and pushes them
#   dnd-scribe    read   the server only reads Discord archives out of it
#
# So there is an ssh config with a host alias per repo, which is the usual way
# around GitHub's one-key-one-repo rule.
#
# This script generates the keys, writes the config, points the remotes at the
# right aliases, and then stops and prints what you have to paste into GitHub.
# It cannot do that part: adding a key to a repository needs your login.
#
# Safe to run twice. Existing keys are kept rather than replaced, because
# replacing one silently would break access that already works.

set -euo pipefail

ROOT="$HOME/dnd-universe"
SCRIBE="$HOME/dnd-scribe"
OWNER="slambdi99-cyber"

mkdir -p ~/.ssh
chmod 700 ~/.ssh

make_key() {
    local name="$1"
    if [ -f "$HOME/.ssh/$name" ]; then
        echo "   keeping the existing $name key"
    else
        ssh-keygen -t ed25519 -q -N "" -C "buried-star server ($name)" \
            -f "$HOME/.ssh/$name"
        echo "   made a new key for $name"
    fi
}

echo "== keys"
make_key dnd-universe
make_key dnd-scribe

echo
echo "== ssh config"
if grep -q "Host github-dnd-universe" ~/.ssh/config 2>/dev/null; then
    echo "   already there"
else
    cat >> ~/.ssh/config <<EOF

# One key per repository, because GitHub will not take the same deploy key
# twice. The alias in the remote URL is what picks the key.
Host github-dnd-universe
    HostName github.com
    User git
    IdentityFile ~/.ssh/dnd-universe
    IdentitiesOnly yes

Host github-dnd-scribe
    HostName github.com
    User git
    IdentityFile ~/.ssh/dnd-scribe
    IdentitiesOnly yes
EOF
    chmod 600 ~/.ssh/config
    echo "   written"
fi

echo
echo "== remotes"
if [ -d "$ROOT/.git" ]; then
    git -C "$ROOT" remote set-url origin \
        "git@github-dnd-universe:$OWNER/dnd-universe.git"
    echo "   dnd-universe points at its key"
fi
if [ -d "$SCRIBE/.git" ]; then
    git -C "$SCRIBE" remote set-url origin \
        "git@github-dnd-scribe:$OWNER/dnd-scribe.git"
    echo "   dnd-scribe points at its key"
fi

cat <<EOF

================================================================
Now the part only you can do. Two keys, two repositories, and the
write box matters.

1. github.com/$OWNER/dnd-universe/settings/keys
   Add deploy key. Title: buried-star server
   TICK "Allow write access". The server has to push what people
   write on the site, and without this it silently cannot.

$(cat ~/.ssh/dnd-universe.pub)

2. github.com/$OWNER/dnd-scribe/settings/keys
   Add deploy key. Title: buried-star server
   Leave write access OFF. This one only reads.

$(cat ~/.ssh/dnd-scribe.pub)

================================================================

When both are pasted in, check them:

  ssh -T git@github-dnd-universe
  ssh -T git@github-dnd-scribe

Each should greet you by repository name. "Permission denied" means
the key is not pasted in yet.
EOF
