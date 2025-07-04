export const SPEED_OPTIONS = [
    { label: "Auto", value: 255 },
    { label: "Tari=25us, FM0, LHF=40KHz", value: 0 },
    { label: "Tari=25us, Miller4, LHF=250KHz", value: 1 },
    { label: "Tari=25us, Miller4, LHF=300KHz", value: 2 },
    { label: "Fast Mode | Tari=6.25us, FM0, LHF=400KHz", value: 3 },
    { label: "Tari=25us, Miller4, LHF=320KHz", value: 4 },
    // { label: "Reserved", value: 5 }, // 5-254 reserved
  ]

export const Q_VALUE_OPTIONS = Array.from({ length: 16 }, (_, i) => ({
    label: `${i}`,
    value: i,
    })).map((opt) => ({ ...opt,
    label: opt.value === 0 ? "0 | Single" : opt.value === 4 ? "4 | Multi" : `${opt.value}`,
    value: opt.value,           
}))

export const SESSION_OPTIONS = [
    { label: "0", value: 0 },
    { label: "1", value: 1 },
    { label: "2", value: 2 },
    { label: "3", value: 3 },
  ]

export const INVENTORY_FLAG_OPTIONS = [
    { label: "Flag A", value: 0 },
    { label: "Flag B", value: 1 },
    { label: "Alternate Flag A/B (double-sided)", value: 2 },
]