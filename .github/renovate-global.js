// Global (self-hosted) Renovate configuration.
// A .js config is used instead of .json5 so the private-registry password can
// be read from the environment (set as a GitHub secret in renovate.yml).
//
// Per-repo behavior lives in each repo's renovate.json (created by the
// onboarding PR); this file only configures the bot itself.

module.exports = {
  platform: 'github',
  autodiscover: true,
  autodiscoverFilter: ['dev-lukas/*'],
  onboarding: true,
  onboardingConfig: {
    $schema: 'https://docs.renovatebot.com/renovate-schema.json',
    extends: ['config:recommended', ':dependencyDashboard'],
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
  ],
};
