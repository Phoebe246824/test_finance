import { defineStore } from 'pinia'
import { getAppSettings, type SystemConfig } from '../api/settings'
import { defaultSystemConfig } from '../views/settings/helpers'

type AppSettingsState = {
  systemConfig: SystemConfig
  loaded: boolean
}

export const useAppSettingsStore = defineStore('appSettings', {
  state: (): AppSettingsState => ({
    systemConfig: { ...defaultSystemConfig },
    loaded: false,
  }),
  getters: {
    appName: (state) => state.systemConfig.name,
    appDescription: (state) => state.systemConfig.description,
  },
  actions: {
    applySystemConfig(config: SystemConfig) {
      this.systemConfig = { ...config }
      this.loaded = true
      document.title = config.name
    },
    async load() {
      const data = await getAppSettings()
      this.applySystemConfig(data.settings.system_config || defaultSystemConfig)
    },
  },
})
