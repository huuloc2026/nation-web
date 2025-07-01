import { useEffect, useState } from "react"
import { Wifi, WifiOff, Radio, Activity, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  SPEED_OPTIONS,
  Q_VALUE_OPTIONS,
  SESSION_OPTIONS,
  INVENTORY_FLAG_OPTIONS,
} from "@/lib/baseband.constant"
import { Checkbox } from "@/components/ui/checkbox"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { detectPorts, getAntennaPower, setAntennaPower, enableAntennas, disableAntennas, getReaderInfo, configureBaseband, queryBasebandProfile } from "@/api/rfid"

interface AntennaSettings {
  antenna1: boolean
  antenna2: boolean
  antenna3: boolean
  antenna4: boolean
  [key: string]: boolean
}

interface SidebarProps {
  className?: string
  isConnected: boolean
  serialPort: string
  setSerialPort: (value: string) => void
  baudRate: string
  setBaudRate: (value: string) => void
  handleConnect: () => void
  antennaSettings: AntennaSettings
  setAntennaSettings: React.Dispatch<React.SetStateAction<AntennaSettings>>
  handleAntennaChange: (antenna: keyof AntennaSettings, checked: boolean) => void

  handleGetPower?: () => Promise<void>
  handleSetPower?: () => Promise<void>
}
export function Sidebar({
  className,
  isConnected,
  serialPort,
  setSerialPort,
  baudRate,
  setBaudRate,
  handleConnect,
  antennaSettings,
  setAntennaSettings,
  handleAntennaChange,
}: SidebarProps) {
  const [powers, setPowers] = useState<{ [key: number]: number }>({
    1: 0,
    2: 0,
    3: 0,
    4: 0,
  })

  const [preserveConfig, setPreserveConfig] = useState(true)
  const [loading, setLoading] = useState(false)
  const [detectingPort, setDetectingPort] = useState(false)
  const [readerInfo, setReaderInfo] = useState<any>(null)
  const [infoLoading, setInfoLoading] = useState(false)

  // Baseband state
  const [baseband, setBaseband] = useState({
    speed: 0,
    q_value: 1,
    session: 2,
    inventory_flag: 0,
  })

  const [basebandProfile, setBasebandProfile] = useState<any>(null)
  const [basebandLoading, setBasebandLoading] = useState(false)

  const handleGetPower = async () => {
    setLoading(true)
    try {
      const res = await getAntennaPower()
      if (res.success && res.data) {
        setPowers({
          1: res.data[1] ?? 20,
          2: res.data[2] ?? 20,
          3: res.data[3] ?? 20,
          4: res.data[4] ?? 20,
        })
        toast("Đã lấy thông tin công suất antennas.", { description: "Get Power" })
      } else {
        toast("Không thể lấy thông tin công suất.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
      }
    } catch (e) {
      toast("Không thể lấy thông tin công suất.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setLoading(false)
  }

  const handleSetPower = async () => {
    setLoading(true)
    try {
      const res = await setAntennaPower(powers, preserveConfig)
      if (res.success) {
        toast("Đã thiết lập công suất antennas.", { description: "Set Power" })
      } else {
        toast(res.message || "Không thể thiết lập công suất.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
      }
    } catch (e) {
      toast("Không thể thiết lập công suất.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setLoading(false)
  }

  const handleGetAntenna = async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/get_enabled_antennas")
      const data = await res.json()
      if (data.success && Array.isArray(data.antennas)) {
        setAntennaSettings((prev) => {
          const updated = { ...prev }
          Object.keys(updated).forEach((key) => {
            const antNum = Number(key.replace("antenna", ""))
            updated[key] = data.antennas.includes(antNum)
          })
          return updated
        })
        toast("Đã lấy trạng thái antenna.", { description: "Get Antenna" })
      } else {
        toast("Không thể lấy trạng thái antenna.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
      }
    } catch (e) {
      toast("Không thể lấy trạng thái antenna.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setLoading(false)
  }

  const handleSetAntenna = async () => {
    setLoading(true)
    try {
      const enabledAnts = Object.entries(antennaSettings)
        .filter(([_, v]) => v)
        .map(([k]) => Number(k.replace("antenna", "")))
      const disabledAnts = Object.entries(antennaSettings)
        .filter(([_, v]) => !v)
        .map(([k]) => Number(k.replace("antenna", "")))
      if (enabledAnts.length > 0) await enableAntennas(enabledAnts)
      if (disabledAnts.length > 0) await disableAntennas(disabledAnts)
      toast("Đã thiết lập trạng thái antenna.", { description: "Set Antenna" })
    } catch (e) {
      toast("Không thể thiết lập trạng thái antenna.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setLoading(false)
  }

  // Add browser-side auto-detect RS232 port (Web Serial API)
  const handleDetectPort = async () => {
    // Try browser Web Serial API first
    if ("serial" in navigator) {
      try {
        // Prompt user to select a serial port
        // Filters can be added for USB vendor/product if needed
        // @ts-ignore
        const port = await (navigator as any).serial.requestPort?.()
        if (port) {
          // Try to get info (USB vendor/product) if available
          // @ts-ignore
          const info = port.getInfo?.()
          // Compose a display string (not always available)
          let portLabel = ""
          if (info) {
            if (info.usbVendorId && info.usbProductId) {
              portLabel = `USB VID: ${info.usbVendorId.toString(16)}, PID: ${info.usbProductId.toString(16)}`
            }
          }
          // Web Serial API does not provide a system path, so just show "Browser Serial"
          setSerialPort("browser-serial")
          toast("Đã chọn cổng RS232 qua trình duyệt.", { description: portLabel || "Web Serial API" })
          return
        }
      } catch (err) {
        toast("Không thể phát hiện cổng RS232 qua trình duyệt.", { description: String(err), style: { background: "#ef4444", color: "#fff" } })
        // Fallback to backend detection below
      }
    }
    // Fallback: backend auto-detect
    setDetectingPort(true)
    try {
      const res = await detectPorts()
      // res is already the parsed JSON object
      if (res.success && res.port) {
        setSerialPort(res.port)
        toast("Đã phát hiện cổng: " + res.port, { description: "Auto Detect UART" })
      } else {
        toast("Không tìm thấy cổng UART.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
      }
    } catch (e) {
      toast("Không thể phát hiện cổng UART.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setDetectingPort(false)
  }

  const handleConfigureBaseband = async () => {
    setBasebandLoading(true)
    try {
      const res = await configureBaseband(baseband)
      if (res.success) {
        toast("Đã cấu hình baseband thành công.", { description: "Baseband" })
      } else {
        toast(res.message || "Không thể cấu hình baseband.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
      }
    } catch (e) {
      toast("Không thể cấu hình baseband.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setBasebandLoading(false)
  }

  const handleQueryBasebandProfile = async () => {
    setBasebandLoading(true)
    try {
      const res = await queryBasebandProfile()
      if (res.success && res.data) {
        setBasebandProfile(res.data)
        // Fill select fields with queried values (ensure string for Select)
        setBaseband({
          speed: typeof res.data.speed === "number" ? res.data.speed : 0,
          q_value: typeof res.data.q_value === "number" ? res.data.q_value : 1,
          session: typeof res.data.session === "number" ? res.data.session : 2,
          inventory_flag: typeof res.data.inventory_flag === "number" ? res.data.inventory_flag : 0,
        })
        toast("Đã lấy thông tin baseband.", { description: "Baseband" })
      } else {
        setBasebandProfile(null)
        toast(res.message || "Không thể lấy thông tin baseband.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
      }
    } catch (e) {
      setBasebandProfile(null)
      toast("Không thể lấy thông tin baseband.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setBasebandLoading(false)
  }

  useEffect(() => {
    if (isConnected) {
      setInfoLoading(true)
      getReaderInfo().then((res) => {
        if (res.success && res.data) setReaderInfo(res.data)
        else setReaderInfo(null)
        setInfoLoading(false)
      })
    } else {
      setReaderInfo(null)
    }
  }, [isConnected])

  return (
    <div className={cn("flex h-full w-80 flex-col bg-background border-r", className)}>
      <div className="flex h-14 items-center border-b px-4">
        <Radio className="h-6 w-6 mr-2" />
        <span className="font-semibold">Device Controls</span>
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              {isConnected ? <Wifi className="h-4 w-4 text-green-500" /> : <WifiOff className="h-4 w-4 text-red-500" />}
              Device Connection
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="serialPort" className="text-sm">
                Serial Port
              </Label>
              <div className="flex gap-2">
                <input
                  id="serialPort"
                  type="text"
                  value={serialPort}
                  onChange={(e) => setSerialPort(e.target.value)}
                  className="border rounded px-2 py-1 text-sm flex-1"
                  placeholder="e.g. /dev/ttyUSB0 or COM3"
                  disabled={loading}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="baudRate" className="text-sm">
                Baudrate
              </Label>
              <Select value={baudRate} onValueChange={setBaudRate}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="9600">9600</SelectItem>
                  <SelectItem value="19200">19200</SelectItem>
                  <SelectItem value="38400">38400</SelectItem>
                  <SelectItem value="57600">57600</SelectItem>
                  <SelectItem value="115200">115200</SelectItem>
                  <SelectItem value="230400">230400</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleConnect}
                size="sm"
                variant={isConnected ? "destructive" : "default"}
                className="flex-1"
              >
                {isConnected ? "Disconnect" : "Connect"}
              </Button>
              <Button
                size="sm"
                variant={isConnected ? "default" : "destructive"}
                onClick={handleDetectPort}
                disabled={loading || detectingPort}
                type="button"
              >
                {detectingPort ? "Detecting..." : "Detect"}
              </Button>
            </div>
          </CardContent>
        </Card>


 {/* Baseband Configuration Card */}
 <Card>
  <CardHeader className="pb-3">
    <CardTitle className="flex items-center gap-2 text-base">
      <Zap className="h-4 w-4" />
      Baseband Settings
    </CardTitle>
  </CardHeader>
  <CardContent className="space-y-3">
    <div className="grid grid-cols-2 gap-2">
      <div>
        <Label htmlFor="baseband-speed" className="text-xs">Speed</Label>
        <Select
          value={String(baseband.speed)}
          onValueChange={v => setBaseband(b => ({ ...b, speed: Number(v) }))}
          disabled={basebandLoading}
        >
          <SelectTrigger className="w-full h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SPEED_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={String(opt.value)}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label htmlFor="baseband-q" className="text-xs">Q Value</Label>
        <Select
          value={String(baseband.q_value)}
          onValueChange={v => setBaseband(b => ({ ...b, q_value: Number(v) }))}
          disabled={basebandLoading}
        >
          <SelectTrigger className="w-full h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Q_VALUE_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={String(opt.value)}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label htmlFor="baseband-session" className="text-xs">Session</Label>
        <Select
          value={String(baseband.session)}
          onValueChange={v => setBaseband(b => ({ ...b, session: Number(v) }))}
          disabled={basebandLoading}
        >
          <SelectTrigger className="w-full h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SESSION_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={String(opt.value)}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label htmlFor="baseband-flag" className="text-xs">Inventory Flag</Label>
        <Select
          value={String(baseband.inventory_flag)}
          onValueChange={v => setBaseband(b => ({ ...b, inventory_flag: Number(v) }))}
          disabled={basebandLoading}
        >
          <SelectTrigger className="w-full h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {INVENTORY_FLAG_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={String(opt.value)}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
    <div className="flex gap-2">
      <Button size="sm" onClick={handleConfigureBaseband} className="flex-1" disabled={basebandLoading}>
        {basebandLoading ? "Đang gửi..." : "Set Baseband"}
      </Button>
      <Button size="sm" variant="outline" onClick={handleQueryBasebandProfile} className="flex-1" disabled={basebandLoading}>
        {basebandLoading ? "Đang lấy..." : "Get Baseband"}
      </Button>
    </div>

  </CardContent>
</Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="h-4 w-4" />
              Reader Information
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
          {infoLoading ? (
            <div className="text-sm text-muted-foreground">Loading...</div>
          ) : readerInfo ? (
            Object.entries(readerInfo).map(([k, v]) => (
              <div key={k} className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">{k}:</span>
                <span className="text-sm font-medium">{String(v)}</span>
              </div>
            ))
          ) : (
            <div className="text-sm text-muted-foreground">No reader info</div>
          )}
        </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Zap className="h-4 w-4" />
              Antenna Control
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(antennaSettings).map(([key, value]) => (
                <div key={key} className="flex items-center space-x-2">
                  <Checkbox
                    id={key}
                    checked={value}
                    onCheckedChange={(checked) =>
                      handleAntennaChange(key as keyof typeof antennaSettings, checked as boolean)
                    }
                  />
                  <Label htmlFor={key} className="text-sm font-medium">
                    Antenna {key.slice(-1)}
                  </Label>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={handleGetAntenna} className="flex-1" disabled={loading}>
                {loading ? "Đang lấy..." : "Get Antenna"}
              </Button>
              <Button size="sm" onClick={handleSetAntenna} className="flex-1" disabled={loading}>
                {loading ? "Đang gửi..." : "Set Antenna"}
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[1, 2, 3, 4].map((ant) => (
                <div key={ant} className="flex flex-col space-y-1">
                  <Label htmlFor={`powerInput${ant}`} className="text-xs">
                    Power Ant {ant}
                  </Label>
                  <input
                    id={`powerInput${ant}`}
                    type="number"
                    min={0}
                    max={30}
                    value={powers[ant]}
                    onChange={(e) =>
                      setPowers((prev) => ({
                        ...prev,
                        [ant]: Number(e.target.value),
                      }))
                    }
                    className="border rounded px-2 py-1 text-sm"
                    disabled={loading}
                  />
                </div>
              ))}
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="preserveConfig"
                checked={preserveConfig}
                onCheckedChange={(checked) => setPreserveConfig(!!checked)}
              />
              <Label htmlFor="preserveConfig" className="text-xs">
                Lưu cấu hình khi tắt nguồn
              </Label>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={handleGetPower} className="flex-1" disabled={loading}>
                {loading ? "Đang lấy..." : "Get Power"}
              </Button>
              <Button size="sm" onClick={handleSetPower} className="flex-1" disabled={loading}>
                {loading ? "Đang gửi..." : "Set Power"}
              </Button>
            </div>
          </CardContent>
        </Card>

       
      </div>
    </div>
  )
}