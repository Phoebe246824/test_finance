<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <strong>Sentinel Edge</strong>
        <span>金融风控智能体</span>
      </div>
      <nav class="nav-list">
        <RouterLink class="nav-link" to="/analysis">风险分析</RouterLink>
        <RouterLink class="nav-link" to="/events">事件库</RouterLink>
        <RouterLink class="nav-link" to="/graph/person">人物图谱</RouterLink>
        <RouterLink class="nav-link" to="/blacklist">黑名单</RouterLink>
        <RouterLink class="nav-link" to="/system">系统状态</RouterLink>
      </nav>
    </aside>
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>
