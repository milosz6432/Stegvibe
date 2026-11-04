import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

interface UiState {
  /** The case shown in the top bar. Navigation always works without one. */
  activeCaseId: string | null
  setActiveCase: (id: string | null) => void
  hexPageSize: number
  setHexPageSize: (n: number) => void
}

// localStorage can be unavailable or throw (private mode, blocked storage): fall back to memory.
const safeStorage = createJSONStorage<Pick<UiState, 'activeCaseId' | 'hexPageSize'>>(() => {
  try {
    const k = '__spectra_probe__'
    window.localStorage.setItem(k, '1')
    window.localStorage.removeItem(k)
    return window.localStorage
  } catch {
    const mem = new Map<string, string>()
    return {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => void mem.set(k, v),
      removeItem: (k: string) => void mem.delete(k),
    }
  }
})

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      activeCaseId: null,
      setActiveCase: (id) => set({ activeCaseId: id }),
      hexPageSize: 512,
      setHexPageSize: (n) => set({ hexPageSize: n }),
    }),
    {
      name: 'spectra-ui',
      storage: safeStorage,
      partialize: (s) => ({ activeCaseId: s.activeCaseId, hexPageSize: s.hexPageSize }),
    },
  ),
)
