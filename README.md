# bitcoinix.net

This repository contains the files for the official
[bitcoinix.net](https://bitcoinix.net) website, served by GitHub Pages.

The site is static HTML without a build step and without third-party
resources. Its only external request is to the GitHub API, for the
latest release number.

| File | Purpose |
| --- | --- |
| `index.html`, `style.css` | The page |
| `release.js` | Shows the latest release in the footer (optional; the page works without it) |
| `og-image.png` | Social media preview image (1200×630) |
| `robots.txt`, `sitemap.xml` | Search engine hints |
| `.well-known/security.txt` | Security contact ([RFC 9116](https://www.rfc-editor.org/rfc/rfc9116)). **Update `Expires` before it passes.** |
| `flake.nix`, `ci/` | The checks, see below |

The Content Security Policy is set in a `<meta>` tag in `index.html`.
If you add a resource from another origin, add the origin to the policy.

## Checks and deployment

Run the checks before opening a pull request:

```sh
nix flake check
```

They check the site as it is published (`nix build` builds it into `result/`):

- `html`: HTML and CSS validity, with the [Nu Html Checker](https://validator.github.io/validator/)
- `site`: that every link to the site and every resource points to a
  published file, that the Content Security Policy allows everything the page
  loads, and that JSON-LD, `sitemap.xml`, `robots.txt` and `security.txt` are
  valid
- `javascript`: JavaScript syntax

Only the files listed in `siteFiles` in `flake.nix` are published. **Add a new
file there**, or the `site` check fails because the page refers to a file that
isn't published.

Two checks depend on the current date or on other sites, so they run as apps,
weekly in CI:

```sh
nix run .#security-txt-expiry   # fails 30 days before security.txt expires
nix run .#link-check            # checks the external links
```

The [workflow](.github/workflows/site.yml) runs the checks on every pull
request and push. A push to `main` is deployed to GitHub Pages only after the
checks pass, and the workflow then checks that the site serves the checked
files.

## Security

See [SECURITY.md](SECURITY.md).
