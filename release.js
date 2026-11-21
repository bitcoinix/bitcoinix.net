// Shows the latest release tag in the footer. Without JavaScript, or when the
// GitHub API is unavailable or rate-limited, the link still points to the
// latest release on GitHub.
(function () {
  "use strict";

  var repo = "https://github.com/bitcoinix/bitcoinix";
  var link = document.getElementById("latest-release");
  if (!link || !window.fetch) return;

  fetch("https://api.github.com/repos/bitcoinix/bitcoinix/releases/latest", {
    credentials: "omit",
    referrerPolicy: "no-referrer"
  })
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (release) {
      // Only display data in the expected format, and build the URL locally
      // instead of trusting the URL in the API response.
      var tag = String(release.tag_name);
      if (!/^v\d+\.\d+\.\d+$/.test(tag)) return;
      var date = String(release.published_at).slice(0, 10);
      var hasDate = /^\d{4}-\d{2}-\d{2}$/.test(date);

      link.textContent = "Latest release " + tag + (hasDate ? " (" + date + ")" : "");
      link.href = repo + "/releases/tag/" + tag;
    })
    .catch(function () {});
})();
