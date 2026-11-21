{
  description = "The bitcoinix.net website";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;

      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # The files that are published. Everything else in this repository
      # (README, LICENSE, CI config, CNAME, ...) stays unpublished.
      siteFiles = lib.fileset.unions [
        ./index.html
        ./style.css
        ./release.js
        ./logo.png
        ./logo-text.png
        ./apple-touch-icon.png
        ./og-image.png
        ./robots.txt
        ./sitemap.xml
        ./.well-known/security.txt
      ];
    in
    {
      packages = forAllSystems (pkgs: {
        # The site as deployed to GitHub Pages
        default = pkgs.runCommand "bitcoinix.net" { } ''
          cp -r ${
            lib.fileset.toSource {
              root = ./.;
              fileset = siteFiles;
            }
          } $out
        '';
      });

      checks = forAllSystems (
        pkgs:
        let
          site = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          check =
            name: nativeBuildInputs: script:
            pkgs.runCommand "bitcoinix.net-${name}" { inherit nativeBuildInputs; } ''
              ${script}
              touch $out
            '';
        in
        {
          # HTML and CSS against the WHATWG and CSS specs (W3C Nu validator).
          # Warnings fail too, except that `role="list"` on the lists styled
          # with `list-style: none` is intended: Safari drops list semantics
          # without it.
          html = check "html" [ pkgs.validator-nu ] ''
            vnu --Werror --also-check-css \
              --filterpattern '.*The .list. role is unnecessary for element .ul.\.' \
              ${site}/index.html ${site}/style.css
          '';

          # References, Content Security Policy, JSON-LD, XML and security.txt
          site = check "site" [ pkgs.python3 ] ''
            python3 -I ${./ci/check-site.py} ${site}
          '';

          javascript = check "javascript" [ pkgs.nodejs ] ''
            for f in ${site}/*.js; do
              node --check "$f"
            done
          '';
        }
      );

      apps = forAllSystems (
        pkgs:
        let
          site = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          app = name: description: runtimeInputs: text: {
            type = "app";
            program = lib.getExe (pkgs.writeShellApplication { inherit name runtimeInputs text; });
            meta.description = description;
          };
        in
        {
          # Fails when security.txt expires within 30 days, or when it expires
          # more than a year ahead (RFC 9116, section 2.5.5). This depends on
          # the current date, so it is not a flake check: a passing check
          # would stay cached and never run again.
          security-txt-expiry =
            app "security-txt-expiry" "Check that security.txt doesn't expire soon" [ pkgs.python3 ]
              ''
                python3 -I ${./ci/check-security-txt-expiry.py} ${site}/.well-known/security.txt
              '';

          # Checks the external links. Network-dependent and therefore run on
          # a schedule, not on pull requests. Links to bitcoinix.net itself
          # are checked offline by `checks.site`. x.com refuses automated
          # requests.
          link-check = app "link-check" "Check the external links of the site" [ pkgs.lychee ] ''
            lychee --no-progress --max-retries 3 \
              --exclude '^https://bitcoinix\.net/' \
              --exclude '^https://x\.com/' \
              ${site}/index.html ${site}/.well-known/security.txt
          '';
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
