import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import AnalyzeView from '../views/AnalyzeView.vue'
import EventsView from '../views/EventsView.vue'
import EventDetailView from '../views/EventDetailView.vue'
import BlacklistView from '../views/BlacklistView.vue'
import SystemStatusView from '../views/SystemStatusView.vue'
import PersonGraphView from '../views/PersonGraphView.vue'
import RiskRulesView from '../views/RiskRulesView.vue'
import SettingsView from '../views/SettingsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: DashboardView },
    { path: '/dashboard', component: DashboardView },
    { path: '/analysis', component: AnalyzeView },
    { path: '/events', component: EventsView },
    { path: '/events/:eventId', component: EventDetailView },
    { path: '/graph/person', component: PersonGraphView },
    { path: '/blacklist', component: BlacklistView },
    { path: '/settings', component: SettingsView },
    { path: '/risk-rules', component: RiskRulesView },
    { path: '/system', component: SystemStatusView },
  ],
})
