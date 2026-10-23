// Playbook step 2: name each candidate checkout by its role in integration/COMPATIBILITY.json `repositories`
// (read-only: it runs `git remote -v` and changes nothing).
//
//   node roles.mjs <checkout>...
//
// Every fetch URL of a checkout's remotes is reduced to `owner/repo`, lower case, without a trailing `/` or `.git`
// (GitHub compares owner and repository names without case), and matched against `repositories`, reduced the same way;
// `translator_mirror` is the former path of `translator` (GitHub redirects it), so it names the role `translator`.
// Only these forms name a repository: a GitHub URL (`https://github.com/<owner>/<repo>`, `ssh://git@github.com/...`,
// `git@github.com:<owner>/<repo>`), a git proxy on this machine's loopback that serves GitHub repositories under
// `/git/<owner>/<repo>` (`http://<user>@127.0.0.1:<port>/git/<owner>/<repo>`, also `localhost` and `[::1]`), and a bare
// `<owner>/<repo>` (the form the website's vendored SOURCE.json files use). Any other host, a local path or a file URL
// names no role, whatever its last two path segments say: roles.mjs names that remote on standard error.
// Prints `<role>  <checkout>  <remote>  <url>` for each match (the URL without any user name or password it carries), or
// `none  <checkout>` when no remote of the checkout matches; exit status 1 when a checkout matches no role.
import { execFileSync } from "node:child_process";
import { readFileSync, realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Roles that are another name of a role: the former path of the organization's translator repository. */
export const ALIASES = Object.freeze({ translator_mirror: "translator" });

const GITHUB_HOSTS = new Set(["github.com", "www.github.com"]);
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);
const NAME = /^[A-Za-z0-9_.-]+$/;

/** `owner/repo` (lower case) of path segments that are exactly an owner and a repository, else null. */
function twoSegments(segments) {
  const parts = segments.filter((p) => p.length > 0);
  if (parts.length !== 2) return null;
  const [owner, repo] = [parts[0], parts[1].replace(/\.git$/i, "")];
  return NAME.test(owner) && NAME.test(repo) && repo.length > 0 ? `${owner}/${repo}`.toLowerCase() : null;
}

/** `owner/repo` of a repository URL or name, lower case; null when it is not one of the forms above. */
export function ownerRepo(url) {
  if (typeof url !== "string") return null;
  const text = url.trim();
  if (/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(text)) {
    let u;
    try {
      u = new URL(text);
    } catch {
      return null;
    }
    const host = u.hostname.toLowerCase();
    const segments = u.pathname.split("/");
    if (["https:", "http:", "ssh:", "git:"].includes(u.protocol) && GITHUB_HOSTS.has(host)) return twoSegments(segments);
    if (["https:", "http:"].includes(u.protocol) && LOOPBACK_HOSTS.has(host)) {
      const parts = segments.filter((p) => p.length > 0);
      return parts.length === 3 && parts[0] === "git" ? twoSegments(parts.slice(1)) : null;
    }
    return null;
  }
  const scp = text.match(/^(?:[^@/:]+@)?([A-Za-z0-9.-]+):(.*)$/);
  if (scp) return GITHUB_HOSTS.has(scp[1].toLowerCase()) ? twoSegments(scp[2].split("/")) : null;
  return /^[^/]+\/[^/]+$/.test(text.replace(/\/+$/, "")) ? twoSegments(text.split("/")) : null;
}

/** A URL as it may be printed: without the user name or password a URL can carry (a token can stand in either), so no
 * credential reaches a report; ssh's conventional user `git` stays. */
export function printable(url) {
  return typeof url === "string" ? url.replace(/^([A-Za-z][A-Za-z0-9+.-]*:\/\/)([^/@]*)@/, (all, scheme, user) => (user === "git" ? all : scheme)) : url;
}

/** The roles (keys of `repositories`, aliases resolved) whose repository is the one `url` names. */
export function rolesOf(url, repositories) {
  const name = ownerRepo(url);
  if (name === null) return [];
  const roles = [];
  for (const [key, value] of Object.entries(repositories ?? {})) {
    const role = Object.hasOwn(ALIASES, key) ? ALIASES[key] : key;
    if (ownerRepo(value) === name && !roles.includes(role)) roles.push(role);
  }
  return roles;
}

/** The fetch remotes of a checkout: [[remote, url], ...] (none when it is not a git checkout). */
export function fetchRemotes(checkout) {
  let out = "";
  try {
    out = execFileSync("git", ["-C", checkout, "remote", "-v"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  } catch {
    return [];
  }
  return out.split("\n").map((line) => line.match(/^(\S+)\s+(\S+)\s+\(fetch\)$/)).filter(Boolean).map((m) => [m[1], m[2]]);
}

function main(checkouts) {
  if (checkouts.length === 0) {
    console.error("usage: roles.mjs <checkout>...");
    return 2;
  }
  const compat = JSON.parse(readFileSync(fileURLToPath(new URL("../COMPATIBILITY.json", import.meta.url)), "utf8"));
  let unmatched = 0;
  for (const checkout of checkouts) {
    let matched = false;
    for (const [remote, url] of fetchRemotes(checkout)) {
      if (ownerRepo(url) === null) {
        console.error(`roles.mjs: ${checkout} ${remote} ${printable(url)}: not a GitHub URL, a loopback git proxy's /git/<owner>/<repo> or <owner>/<repo>: no role`);
        continue;
      }
      for (const role of rolesOf(url, compat.repositories)) {
        matched = true;
        console.log(`${role}  ${checkout}  ${remote}  ${printable(url)}`);
      }
    }
    if (!matched) {
      unmatched += 1;
      console.log(`none  ${checkout}`);
    }
  }
  return unmatched === 0 ? 0 : 1;
}

// Run as a script (not when check-agents.mjs imports ownerRepo): the real paths compare, so a symlinked kit path runs it too.
const invoked = (() => {
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
})();
if (invoked) process.exit(main(process.argv.slice(2)));
