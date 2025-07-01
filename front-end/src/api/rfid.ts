// Generic API call utility
export async function apiCall<T = any>(
  url: string,
  method: "GET" | "POST" = "GET",
  data?: any
): Promise<T> {
  const options: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
  }
  if (data) options.body = JSON.stringify(data)
  const res = await fetch(url, options)
  // Fix: handle empty response body gracefully
  const text = await res.text()
  if (!text) return {} as T
  try {
    return JSON.parse(text)
  } catch {
    return {} as T
  }
}

// Connect to RFID reader
export async function connectReader(port: string, baudrate: number) {
  return apiCall("/api/connect", "POST", { port, baudrate })
}

// Disconnect from RFID reader
export async function disconnectReader() {
  return apiCall("/api/disconnect", "POST")
}

// Start inventory
export async function startInventory(target: number = 0) {
  return apiCall("/api/start_inventory", "POST", { target })
}

// Stop inventory
export async function stopInventory() {
  return apiCall("/api/stop_inventory", "POST")
}

// Get Power Level
export async function getAntennaPower() {
  return apiCall("/api/get_antenna_power", "GET")
}

// Set Power Level
export async function setAntennaPower(
  powers: { [key: number]: number },
  preserveConfig: boolean = true
) {
  return apiCall("/api/set_power", "POST", { powers, preserveConfig })
}

// Enable antennas (expects array of antenna numbers)
export async function enableAntennas(
  antennas: number[],
  saveOnPowerDown: boolean = true
) {
  return apiCall("/api/enable_antennas", "POST", {
    antennas,
    save_on_power_down: saveOnPowerDown,
  })
}

// Disable antennas (expects array of antenna numbers)
export async function disableAntennas(
  antennas: number[],
  saveOnPowerDown: boolean = true
) {
  return apiCall("/api/disable_antennas", "POST", {
    antennas,
    save_on_power_down: saveOnPowerDown,
  })
}

// handle dectect port
export async function detectPorts() {
  return apiCall("/api/auto_detect_uart", "GET")
}

export async function getReaderInfo() {
  return apiCall("/api/reader_info", "GET")
}

// Configure baseband parameters
export async function configureBaseband(params: {
  speed: number
  q_value: number
  session: number
  inventory_flag: number
}) {
  return apiCall("/api/configure_baseband", "POST", params)
}

// Query current baseband profile
export async function queryBasebandProfile() {
  return apiCall("/api/query_baseband_profile", "GET")
}