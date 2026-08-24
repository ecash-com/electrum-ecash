# Reporting a vulnerability

**This is Electrum eCash, a fork.** Report issues here, not to the Electrum
developers — they do not maintain this software and cannot fix it.

## In this fork's own code

Anything in the ECX changes — the fork's ~30 commits on top of upstream `4.8.1`,
listed by `git log 4.8.1..ecx/4.8.1` or `grep -rn '# ECX:' electrum/` — should be
reported privately here:

- (preferred) GitHub's ["Report a
  vulnerability"](https://github.com/ecash-com/electrum-ecash/security/advisories/new)
  flow on this repository, or
- a private message to the maintainers via the contacts on
  <https://ecash.com>.

Please do not open a public issue for anything that could put funds at risk
before it is fixed.

> **TODO before release:** publish maintainer email addresses and GPG
> fingerprints here, and a key in `pubkeys/`, so reports can be sent encrypted.
> Until that exists, GitHub's private advisory flow is the only confidential
> channel this project offers.

## In unmodified upstream code

If the bug is in Electrum itself and is not caused by our changes, it affects
Bitcoin Electrum users too, and upstream should hear about it first. Follow
<https://github.com/spesmilo/electrum/blob/master/SECURITY.md> and report it to
them — **do not** post it publicly here in the meantime. Let us know afterwards
so we can pick up their fix.

## Known accepted risks

Some are structural to this chain rather than bugs; see
[FORK.md](FORK.md#known-gaps).

- **ECX and Bitcoin addresses are identical.** Nothing in an address or a
  transaction distinguishes the chains. Much of this fork exists to stop that
  ambiguity turning into lost funds.
- **The server sees your addresses.** Electrum's light-client model hands the
  server your wallet's address set, and because pre-fork addresses are shared,
  an ECX server operator learns your *Bitcoin* addresses too.
- **No signed releases yet.** There are no official binaries. Anything
  distributed as a signed release of this project right now is not from us.
