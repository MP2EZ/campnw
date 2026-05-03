module.exports = {
  ci: {
    collect: {
      staticDistDir: "./web/dist",
      // Only audit "/" — /plan and /map are SPA routes served by the same
      // index.html bundle, so the static dist server returns 404 for them.
      // Auditing the bundle once at "/" covers what those routes would.
      url: ["/"],
    },
    assert: {
      assertions: {
        "categories:performance": ["warn", { minScore: 0.85 }],
        "categories:accessibility": ["error", { minScore: 0.95 }],
        "categories:best-practices": ["error", { minScore: 0.9 }],
      },
    },
    upload: { target: "temporary-public-storage" },
  },
};
