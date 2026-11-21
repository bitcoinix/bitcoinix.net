# bitcoinix.net

This repository contains the files for the official
[bitcoinix.net](https://bitcoinix.net) website, served by GitHub Pages
from the `main` branch.

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
| `.nojekyll` | Turns off Jekyll, so `.well-known/` is published |

The Content Security Policy is set in a `<meta>` tag in `index.html`.
If you add a resource from another origin, add the origin to the policy.

## Security

See [SECURITY.md](SECURITY.md).
