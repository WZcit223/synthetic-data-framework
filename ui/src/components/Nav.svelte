<!--
  The header every rebuilt page shares: the title and the links to every page.
  A new page adds its link here once (docs/refactor/frontend/interfaces.md §1.4).
-->
<script>
  /** @type {{current: string, children?: import("svelte").Snippet}} */
  let { current, children } = $props();

  const PAGES = [
    ["index.html", "Dashboard"],
    ["explore.html", "Explore"],
    ["synthesizers.html", "Synthesizers"],
    ["effects.html", "Effects"],
    ["forecasts.html", "Forecasts"],
  ];
</script>

<header>
  <h1>🧩 Synthetic Data Framework <span class="muted">— AI Warehouse</span></h1>
  <nav aria-label="Pages">
    {#each PAGES as [href, name] (href)}
      <a {href} aria-current={href === current ? "page" : undefined}>{name}</a>
    {/each}
  </nav>
  {@render children?.()}
</header>

<style>
  header {
    padding: 20px 28px;
    border-bottom: 1px solid var(--rule);
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }
  @media (max-width: 600px) {
    header { padding: 16px; }
  }
  h1 {
    font-size: 18px;
    margin: 0;
    font-weight: 650;
  }
  nav {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  a {
    color: var(--ink-muted);
    text-decoration: none;
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 550;
  }
  a:hover {
    color: var(--ink);
    background: var(--surface-raised);
  }
  a[aria-current="page"] {
    color: var(--ink);
    background: var(--surface-raised);
    box-shadow: inset 0 -2px 0 var(--accent);
  }
</style>
