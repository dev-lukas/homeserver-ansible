// Global (self-hosted) Renovate configuration.
// A .js config is used instead of .json5 so the private-registry password can
// be read from the environment (set as a GitHub secret in renovate.yml).
//
// Per-repo behavior lives in each repo's renovate.json (created by the
// onboarding PR); this file only configures the bot itself.

module.exports = {
  platform: 'github',
  // Only PUBLIC repositories are processed. The list is resolved per run in
  // renovate.yml (the GitHub API endpoint used there only returns public
  // repos) and passed in as a JSON array. No fallback on purpose: a missing
  // env var should fail the run loudly, not silently widen the scope.
  autodiscover: false,
  repositories: JSON.parse(process.env.RENOVATE_PUBLIC_REPOS || '[]'),
  onboarding: true,
  // With an explicit repository list (autodiscover off) Renovate would
  // onboard even repos with zero detected dependencies (profile README
  // etc.) — keep skipping those, like autodiscover mode did.
  onboardingNoDeps: 'disabled',
  onboardingConfig: {
    $schema: 'https://docs.renovatebot.com/renovate-schema.json',
    // group:allNonMajor collapses minor/patch updates into one PR per repo —
    // without it the website repo alone previews ~13 separate minor PRs.
    // Majors stay individual so each can be reviewed on its own.
    extends: ['config:recommended', ':dependencyDashboard', 'group:allNonMajor'],
    timezone: 'Europe/Berlin',
  },
  // Two runs/day; keep PR volume digestible and the CI runner's wake windows
  // short.
  prHourlyLimit: 4,
  prConcurrentLimit: 10,
  timezone: 'Europe/Berlin',
  hostRules: [
    {
      // Lets Renovate resolve references to the private registry (e.g. in
      // compose files) without auth errors. Goes through the public nginx
      // endpoint like every other client.
      hostType: 'docker',
      matchHost: 'registry.lukas-roth.dev',
      username: 'registry',
      password: process.env.RENOVATE_REGISTRY_PASSWORD,
    },
  ],
  packageRules: [
    {
      // Internal CI-built images (SHA/latest tags) are produced by the
      // pipelines, not pulled from upstream — nothing to "update". Flip this
      // rule to { pinDigests: true } instead if digest pinning is ever wanted.
      matchDatasources: ['docker'],
      matchPackageNames: ['registry.lukas-roth.dev/**'],
      enabled: false,
    },
    {
      // Immich pins its companion postgres image per release — bump it when
      // Immich says so, not independently. Major PRs only on explicit
      // approval via the Dependency Dashboard checkbox.
      matchDatasources: ['docker'],
      matchPackageNames: ['ghcr.io/immich-app/postgres'],
      matchUpdateTypes: ['major'],
      dependencyDashboardApproval: true,
    },
    {
      // CI test stacks mirror the production VPS (mariadb/valkey in the
      // backend's docker-compose.test.yml). Major bumps should be a
      // deliberate, prod-synced decision — dashboard approval required.
      matchDatasources: ['docker'],
      matchPackageNames: ['mariadb', 'valkey/valkey'],
      matchUpdateTypes: ['major'],
      dependencyDashboardApproval: true,
    },
  ],
};
