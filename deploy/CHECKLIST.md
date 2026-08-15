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

Oracle Cloud's free tier includes an ARM server, permanently, with no card
charged at the end of a trial. It also includes 10TB of outbound traffic a
month, which is the reason to use Oracle rather than anywhere else: this site
serves 50MB of pictures, and the other free hosts cap outbound traffic at 1GB
and bill you past it.

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com). It wants a card for
   identity checking and does not charge it. Pick a home region close to you
   and stick with it, because you cannot change it later.
2. When the account is ready, go to **Compute** then **Instances** then
   **Create instance**.
3. Change the image to **Canonical Ubuntu 24.04**.

   In the **Image and shape** panel, press **Change image**, tick **Canonical
   Ubuntu**, and then check the version in the list. It offers 20.04, 22.04
   and 24.04, and the one it lands on by default is not always the newest.

   The version cannot be changed after the instance exists, and it matters:
   20.04 ships Python 3.8, while every package here needs 3.10 or newer.

   It is recoverable, just untidy. deadsnakes dropped 20.04 when it went end of
   life, so apt has nothing newer, but a prebuilt standalone Python 3.12 runs
   fine on it and installs in a minute. The real cost of 20.04 is that it left
   standard support in April 2025, so it receives no security patches unless
   you enable Ubuntu Pro, which is free for up to five machines. On a box with
   a public IP that is worth caring about.

   Picking 24.04 here avoids all of it.
4. Change the shape to **Ampere**, **VM.Standard.A1.Flex**, and set it to
   **1 OCPU and 6GB**.

   **Check the shape says "Always Free-eligible" before you create it.** Only
   two shapes are: `VM.Standard.A1.Flex` and `VM.Standard.E2.1.Micro`. During
   the first 30 days the console will happily let you build something else on
   trial credits, and `E5.Flex` in particular looks like an ordinary small
   server. Those get reclaimed or billed when the trial converts.
5. Under **Add SSH keys**, paste the public key you already have rather than
   generating another. Print it with:

   ```bash
   type $env:USERPROFILE\.ssh\oracle-key.pub
   ```

   Reusing it means no new download, no second private key to keep track of,
   and the same `ssh buried-star` afterwards. Generating a fresh pair works
   too, it is just more to carry.
6. Leave the networking defaults alone. Nothing needs to be open to the
   internet: traffic reaches this machine through Tailscale, which dials out
   rather than being dialled into.
7. Create it, and write down the public IP address once it appears.

If you did generate a new pair, Oracle offers that private key once, while the
instance is being created, and never again. Download it before you leave the
page.

Then, on your PC, with the instance's IP address:

```bash
powershell -ExecutionPolicy Bypass -File .\deploy\install-server-key.ps1 -Ip YOUR-IP
```

That takes a newly downloaded key out of Downloads, puts it where ssh looks,
strips the inherited permissions that make ssh refuse it, and writes a config
entry. If there is nothing new in Downloads, it keeps the key you already have
and only updates the address, which is what you want after a rebuild. An
existing key is never overwritten, only renamed, because Oracle will not issue
a replacement.

It also forgets the old server's host key. Without that, connecting to a
rebuilt machine prints a warning about a possible man-in-the-middle attack and
refuses, which is correct behaviour for a real attack and pure noise here.

After that every command below is just:

```bash
ssh buried-star
```

### When it says "out of capacity"

This is the normal experience, not a mistake. Oracle's free ARM capacity is
heavily oversubscribed and the check happens per shape configuration, so the
size you ask for changes your odds a great deal.

Ask for less. 1 OCPU and 6GB gets in where 4 and 24 does not, and the server
does not need more: there is no graphics card work here, just a Python process
serving text and cached thumbnails.

If it still refuses, try the other availability domains, if the create screen
offers any. Smaller regions only have AD-1 and there is nothing to try.

If that fails too, take the AMD instead: shape **VM.Standard.E2.1.Micro**,
1/8 OCPU and 1GB. It is also Always Free, you get two of them, and it is nearly
always available because nobody is competing for it. Everything here works the
same on it. 1GB is tight, so the setup script adds swap when it sees a machine
that small.

What not to do is take whatever the console offers next. Anything outside those
two shapes is a paid instance running on trial credits, and it disappears or
starts billing at the end of the first month. `us-sanjose-1` is a hard region
for ARM capacity, so `E2.1.Micro` is the realistic fallback there.

Retrying at intervals does eventually work if you would rather hold out for the
ARM. There is no trick to it beyond patience.

Every attempt that reaches the key step gives you another key, and the ones for
instances that never got made are dead weight. `install-server-key.ps1` takes
the newest and tells you which it took, so download them all and let it sort
them out.

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
PowerShell on your PC:

```bash
scp C:\Claude\dnd-universe\.wiki-passphrase C:\Claude\dnd-universe\.people-tokens.json C:\Claude\dnd-universe\.session-secret C:\Claude\dnd-universe\.accounts.json buried-star:~/dnd-universe/
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
scp C:\Claude\dnd-universe\.inbox.json buried-star:~/dnd-universe/
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
scp C:\Claude\dnd-scribe\.discord-token buried-star:~/dnd-scribe/
scp C:\Claude\dnd-scribe\.sync-state.json buried-star:~/dnd-scribe/
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
