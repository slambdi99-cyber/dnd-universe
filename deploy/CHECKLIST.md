# Moving the site off your PC

Right now the wiki only exists while your computer is on and Tailscale is
running. Close the PowerShell window, let the machine sleep, go away for a
weekend, and the site is gone for everyone. This moves it to a small free
server that stays on, and leaves your PC responsible for exactly one thing:
drawing pictures, which needs the graphics card.

Everything below is a step only you can do, because each one needs a login or a
secret. The rest is already written and runs on its own.

The steps are in order and each depends on the one before it. Step 5 is the one
to get right: until the server can push, nothing anyone writes on the site
leaves that server.

Budget about half an hour, most of it waiting for Oracle.

---

## 1. Get the machine

Oracle Cloud's free tier includes an ARM server with 4 cores and 24GB of
memory, permanently, with no card charged at the end of a trial. It is far more
than this needs. The catch is that the free ARM capacity is genuinely scarce in
popular regions, so the create button sometimes fails with "out of capacity".
If that happens, try a different availability domain, or try again in a few
hours. It does eventually work.

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com). It wants a card for
   identity checking and does not charge it. Pick a home region close to you
   and stick with it, because you cannot change it later.
2. When the account is ready, go to **Compute** then **Instances** then
   **Create instance**.
3. Change the image to **Canonical Ubuntu 24.04**.
4. Change the shape to **Ampere**, **VM.Standard.A1.Flex**, and set it to
   **4 OCPUs and 24GB**. Taking the whole free allowance costs nothing and
   means you never have to think about it again.
5. Under **Add SSH keys**, choose **Generate a key pair** and download the
   private key. Keep it somewhere you will find again, such as
   `C:\Claude\oracle-key`.
6. Leave the networking defaults alone. Nothing needs to be open to the
   internet: traffic reaches this machine through Tailscale, which dials out
   rather than being dialled into.
7. Create it, and write down the public IP address once it appears.

Then connect from PowerShell:

```bash
ssh -i C:\Claude\oracle-key ubuntu@YOUR-IP
```

If it refuses the key as too open, run
`icacls C:\Claude\oracle-key /inheritance:r /grant:r "$env:USERNAME:R"` and try
again.

---

## 2. Install everything

One command, on the server:

```bash
curl -fsSL https://raw.githubusercontent.com/slambdi99-cyber/dnd-universe/main/deploy/setup.sh | bash
```

It installs Python and Tailscale, clones the repo, sets up the services, and
starts the site. It takes a few minutes, and it is safe to run again if it
stops partway.

When it finishes the wiki is running, but only the server itself can reach it,
there is no passphrase on it, and it is not reading Discord. The next two steps
fix that.

---

## 3. Put it on the internet

Tailscale needs your login, so this cannot be scripted.

```bash
sudo tailscale up
```

It prints a URL. Open it on your PC, sign in with the same account your PC
uses, and approve the machine.

Then give it the name the site will live at, and open the funnel:

```bash
sudo tailscale set --hostname buried-star
sudo tailscale funnel --bg 8787
```

`tailscale funnel status` tells you the address. It will be something like
`https://buried-star.your-tailnet.ts.net`.

**The address changes one last time.** Everyone's browser bookmark and every
MCP connection currently points at your PC. Once this is working, send the new
address to the table and update the connection settings on each machine.

---

## 4. Carry the secrets across

Five files hold everything the server cannot work out for itself. They are all
gitignored, which is why they did not arrive with the clone, and they have to
travel by hand.

I have not touched any of them and will not. Run these yourself, from
PowerShell on your PC, replacing `YOUR-IP`:

```bash
scp -i C:\Claude\oracle-key C:\Claude\dnd-universe\.wiki-passphrase C:\Claude\dnd-universe\.people-tokens.json C:\Claude\dnd-universe\.session-secret C:\Claude\dnd-universe\.accounts.json ubuntu@YOUR-IP:~/dnd-universe/
```

What each one is, so you know what you are moving:

| File | What it is | If you skip it |
|---|---|---|
| `.wiki-passphrase` | The scrypt hash of `PeaPodDungeon`. Not the passphrase itself. | The site has no front door at all. Anyone with the URL walks in. |
| `.people-tokens.json` | One MCP token per person. | Nobody's assistant can connect, and everyone needs a new token. |
| `.session-secret` | Signs the login cookies. | Everyone is logged out, once. Harmless, but they all have to sign in again. |
| `.accounts.json` | Who is signed up. | People have to make their accounts again. |

Optionally bring the two cursors as well. Without them the Discord reader
treats every message it has ever seen as new, and the inbox arrives with
several hundred things in it:

```bash
scp -i C:\Claude\oracle-key C:\Claude\dnd-universe\.inbox.json ubuntu@YOUR-IP:~/dnd-universe/
```

---

## 5. Let the server talk to GitHub

The server needs to push, not just pull. Everything anyone writes on the site
is a commit, and if it cannot push, those commits pile up on a machine nobody
backs up. It also needs to read `dnd-scribe`, which is private.

That is two different levels of access on two repositories, so it is two keys.
GitHub will not accept the same key on both.

On the server:

```bash
~/dnd-universe/deploy/setup-keys.sh
```

It makes both keys, wires up the remotes, and then prints two blocks of text
and stops. Paste each into the repository it names, at **Settings**, **Deploy
keys**, **Add deploy key**.

**Tick "Allow write access" on `dnd-universe`, and leave it off on
`dnd-scribe`.** That one box is the difference between a site that saves what
people write and one that quietly loses it.

Then clone the private repo, which now works:

```bash
git clone git@github-dnd-scribe:slambdi99-cyber/dnd-scribe.git ~/dnd-scribe
```

Then send the bot token across, from your PC:

```bash
scp -i C:\Claude\oracle-key C:\Claude\dnd-scribe\.discord-token ubuntu@YOUR-IP:~/dnd-scribe/
scp -i C:\Claude\oracle-key C:\Claude\dnd-scribe\.sync-state.json ubuntu@YOUR-IP:~/dnd-scribe/
```

And turn the reader on:

```bash
~/dnd-universe/deploy/setup.sh
```

Running setup again is how the Discord timer gets installed. It skips
everything it already did and notices that `dnd-scribe` now exists.

---

## 6. Change what your PC does

Two things change at home.

**Stop starting the server.** `start.ps1` is no longer how the site runs. If it
is still going, close its window. You can leave the scheduled Discord sync
running or turn it off; the server does that job now, and two readers looking
at the same channels is wasteful rather than harmful.

**Start drawing what the site asks for.** When someone presses Art on the
website, the server cannot draw it, so the request goes into the repo instead
and the page says it is waiting for the machine at home. Draining that queue is
one command:

```bash
python tools\draw_queued.py
```

It pulls, draws everything waiting, and pushes the pictures back. They appear
on the site as candidates, and whoever asked picks one.

To make that automatic whenever your PC is on:

```bash
powershell -ExecutionPolicy Bypass -File .\tools\install_draw_schedule.ps1
```

That checks the queue every twenty minutes and does nothing at all when it is
empty.

---

## How to tell it is working

On the server:

```bash
systemctl status buried-star.service
```

`active (running)` is what you want. If it is not, `journalctl -u buried-star
-n 50` says why.

```bash
systemctl list-timers 'buried-star*'
```

Two or three timers, each with a next run time.

The real test is the round trip. On the website, press Art on any page and ask
for something. The page should say it is queued. Run `draw_queued.py` at home,
wait a couple of minutes for the server to pull, and reload the page. The
pictures should be sitting there.

## If something breaks

The site keeps serving whatever it last had, even when the repo sync fails, so
a broken sync is not a broken site. `journalctl -u buried-star-repo -n 30` on
the server says what it could not do. The usual cause is two people editing the
same page from both machines, which stops the sync deliberately rather than
guessing which version wins.

Your PC is still a full copy of everything. If the server is ever lost, a fresh
one takes half an hour and this file.
