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

      # Everything in the repository is published, except these files. A new
      # file for the site needs no change here; a new file that must not be
      # published needs to be added.
      siteFiles = lib.fileset.difference ./. (
        lib.fileset.unions [
          ./.github
          ./.nojekyll
          ./CNAME
          ./LICENSE
          ./README.md
          ./SECURITY.md
          ./ci
          ./flake.lock
          ./flake.nix
        ]
      );
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

          # Links and resources on the site itself point to published files
          # and existing fragments. Offline: https://bitcoinix.net/ is mapped
          # to the built site, and external links are skipped (see
          # apps.link-check). lychee needs CA certificates even offline.
          links = check "links" [ pkgs.lychee pkgs.cacert ] ''
            lychee --offline --no-progress --include-fragments \
              --index-files index.html \
              --remap '^https://bitcoinix\.net/(.*)$ file://${site}/$1' \
              ${site}/index.html ${site}/style.css ${site}/robots.txt \
              ${site}/sitemap.xml ${site}/.well-known/security.txt
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
          # are checked offline by `checks.links`. x.com refuses automated
          # requests.
          #
          # lychee 0.24.2 retries only 429 responses, not 5xx, despite
          # `--max-retries` (fixed by lycheeverse/lychee#2324, not yet
          # released). So a run that finds broken links (exit code 2) is
          # repeated, to ride out transient errors such as GitHub's
          # occasional 503.
          link-check = app "link-check" "Check the external links of the site" [ pkgs.lychee ] ''
            for attempt in 1 2 3; do
                status=0
                lychee --no-progress --max-retries 3 \
                  --exclude '^https://bitcoinix\.net/' \
                  --exclude '^https://x\.com/' \
                  ${site}/index.html ${site}/.well-known/security.txt || status=$?
                if [[ $status != 2 || $attempt == 3 ]]; then
                    exit "$status"
                fi
                echo "Attempt $attempt found broken links, retrying in 2 minutes"
                sleep 120
            done
          '';
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
