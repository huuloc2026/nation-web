import { useState } from "react"
import { Wifi, WifiOff, Radio, Activity, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { getAntennaPower, setAntennaPower } from "@/api/rfid"
import { enableAntennas, disableAntennas } from "@/api/rfid"
interface AntennaSettings {
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
      // You may need to implement /api/get_enabled_antennas on backend
      const res = await fetch("/api/get_enabled_antennas")
      const data = await res.json()
      if (data.success && Array.isArray(data.antennas)) {
        // Update antennaSettings state
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

  // Set Antenna: enable/disable antennas based on UI state
  const handleSetAntenna = async () => {
    setLoading(true)
    try {
      const enabledAnts = Object.entries(antennaSettings)
        .filter(([_, v]) => v)
        .map(([k]) => Number(k.replace("antenna", "")))
      const disabledAnts = Object.entries(antennaSettings)
        .filter(([_, v]) => !v)
        .map(([k]) => Number(k.replace("antenna", "")))
      // Enable selected antennas
      if (enabledAnts.length > 0) await enableAntennas(enabledAnts)
      // Disable unselected antennas
      if (disabledAnts.length > 0) await disableAntennas(disabledAnts)
      toast("Đã thiết lập trạng thái antenna.", { description: "Set Antenna" })
    } catch (e) {
      toast("Không thể thiết lập trạng thái antenna.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setLoading(false)
  }

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
              <Select value={serialPort} onValueChange={setSerialPort}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="COM1">COM1</SelectItem>
                  <SelectItem value="COM2">COM2</SelectItem>
                  <SelectItem value="COM3">COM3</SelectItem>
                  <SelectItem value="COM4">COM4</SelectItem>
                  <SelectItem value="/dev/ttyUSB0">/dev/ttyUSB0</SelectItem>
                  <SelectItem value="/dev/ttyUSB1">/dev/ttyUSB1</SelectItem>
                </SelectContent>
              </Select>
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
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Status:</span>
              <Badge variant={isConnected ? "default" : "destructive"} className="text-xs">
                {isConnected ? "Connected" : "Disconnected"}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Model:</span>
              <span className="text-sm font-medium">RFID-R2000</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Firmware:</span>
              <span className="text-sm font-medium">v2.1.3</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Serial:</span>
              <span className="text-sm font-medium">RF2000-001</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Temperature:</span>
              <span className="text-sm font-medium">42°C</span>
            </div>
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

      <div className="border-t p-4">
        <p className="text-xs text-muted-foreground">IoT Device Manager v1.0</p>
      </div>
    </div>
  )
}