import { useState, useEffect, useRef } from "react"
import { Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { Sidebar } from "./components/Sidebar"
import { TagTable } from "./components/TagTable"
import { connectReader, disconnectReader, startInventory, stopInventory, getTags } from "./api/rfid"
import { toast } from "sonner"

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { InventoryControl } from "./components/InventoryControl"

// Types
export interface Tag {
  id: number
  epc: string
  count: number
  antenna: number | string
  rssi: number
  lastSeen: string
}

export interface AntennaSettings {
  [key: string]: boolean
  antenna1: boolean
  antenna2: boolean
  antenna3: boolean
  antenna4: boolean
}

export default function Dashboard() {
  const [isConnected, setIsConnected] = useState(false)
  const [serialPort, setSerialPort] = useState("/dev/ttyUSB0")
  const [baudRate, setBaudRate] = useState("115200")
  const [detectedTags, setDetectedTags] = useState(0)
  const [totalTags, setTotalTags] = useState(0)
  const [timer, setTimer] = useState("00:00:00")
  const [isInventoryRunning, setIsInventoryRunning] = useState(false)
  const [tags, setTags] = useState<Tag[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Antenna settings
  const [antennaSettings, setAntennaSettings] = useState<AntennaSettings>({
    antenna1: true,
    antenna2: true,
    antenna3: false,
    antenna4: false,
  })

  // Helper: aggregate tags by EPC (count, lastSeen, rssi, antenna)
  function aggregateTags(rawTags: any[]): Tag[] {
    const tagMap = new Map<string, Tag>()
    rawTags.forEach((tag) => {
      const epc = tag.epc
      if (tagMap.has(epc)) {
        const existing = tagMap.get(epc)!
        existing.count += 1
        existing.lastSeen = tag.timestamp // update to latest
        // Optionally update rssi/antenna if needed
        if (tag.rssi > existing.rssi) existing.rssi = tag.rssi
        if (!`${existing.antenna}`.includes(`${tag.antenna}`)) {
          existing.antenna = `${existing.antenna}, ${tag.antenna}`
        }
      } else {
        tagMap.set(epc, {
          id: tagMap.size + 1,
          epc,
          count: 1,
          antenna: tag.antenna,
          rssi: tag.rssi,
          lastSeen: tag.timestamp,
        })
      }
    })
    return Array.from(tagMap.values())
  }

  // Timer effect
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>
    let startTime: number
    if (isInventoryRunning) {
      startTime = Date.now()
      interval = setInterval(() => {
        const elapsed = Date.now() - startTime + elapsedMs
        const hours = Math.floor(elapsed / 3600000)
        const minutes = Math.floor((elapsed % 3600000) / 60000)
        const seconds = Math.floor((elapsed % 60000) / 1000)
        setTimer(
          `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`,
        )
      }, 1000)
    }
    return () => clearInterval(interval)
  }, [isInventoryRunning, elapsedMs])

  // Poll tags from backend when inventory is running
  useEffect(() => {
    if (!isInventoryRunning) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
      return
    }

    pollIntervalRef.current = setInterval(async () => {
      const res = await getTags()
      if (res && res.success && Array.isArray(res.data)) {
        const aggTags = aggregateTags(res.data)
        setTags(aggTags)
        setDetectedTags(aggTags.length)
        setTotalTags(aggTags.reduce((sum, t) => sum + t.count, 0))
      }
    }, 1000)

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [isInventoryRunning])

  const handleConnect = async () => {
    if (!isConnected) {
      const result = await connectReader(serialPort, Number(baudRate))
      if (result.success) setIsConnected(true)
      // handle result.message for user feedback
    } else {
      const result = await disconnectReader()
      if (result.success) setIsConnected(false)
      // handle result.message for user feedback
    }
  }

  const handleStartInventory = async () => {
    setTags([]) // Clear tags on start
    setIsInventoryRunning(true)
    setDetectedTags(0)
    setTotalTags(0)
    await startInventory()
    // Optionally handle result for user feedback
  }

  const handleStopInventory = async () => {
    setIsInventoryRunning(false)
    // Save elapsed time
    const [h, m, s] = timer.split(":").map(Number)
    setElapsedMs(h * 3600000 + m * 60000 + s * 1000)
    await stopInventory()
    // Optionally handle result for user feedback
  }

  const handleClear = () => {
    setTags([])
    setDetectedTags(0)
    setTotalTags(0)
    setTimer("00:00:00")
    setElapsedMs(0)
    setIsInventoryRunning(false)
  }

  const handleGetPower = async () => {
    try {
      // Replace with actual get power logic if available
      toast("Đã lấy thông tin công suất antennas.", {
        description: "Get Power",
      })
    } catch (e) {
      toast("Không thể lấy thông tin công suất.", {
        description: "Lỗi",
        style: { background: "#ef4444", color: "#fff" },
      })
    }
  }

  const handleSetPower = async () => {
    try {
      // Replace with actual set power logic if available
      toast("Đã thiết lập công suất antennas.", {
        description: "Set Power",
      })
    } catch (e) {
      toast("Không thể thiết lập công suất.", {
        description: "Lỗi",
        style: { background: "#ef4444", color: "#fff" },
      })
    }
  }

  const handleAntennaChange = (antenna: keyof AntennaSettings, checked: boolean) => {
    setAntennaSettings((prev) => ({
      ...prev,
      [antenna]: checked,
    }))
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Desktop Sidebar */}
      <div className="hidden lg:block">
        <Sidebar
          isConnected={isConnected}
          serialPort={serialPort}
          setSerialPort={setSerialPort}
          baudRate={baudRate}
          setBaudRate={setBaudRate}
          handleConnect={handleConnect}
          antennaSettings={antennaSettings}
          handleAntennaChange={handleAntennaChange}
        />
      </div>

      {/* Mobile Sidebar */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="p-0 w-80">
          <Sidebar
            isConnected={isConnected}
            serialPort={serialPort}
            setSerialPort={setSerialPort}
            baudRate={baudRate}
            setBaudRate={setBaudRate}
            handleConnect={handleConnect}
            antennaSettings={antennaSettings}
            handleAntennaChange={handleAntennaChange}
            handleGetPower={handleGetPower}
            handleSetPower={handleSetPower}
          />
        </SheetContent>
      </Sheet>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 items-center gap-4 border-b bg-background px-4 lg:px-6">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setSidebarOpen(true)}>
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle sidebar</span>
              </Button>
            </SheetTrigger>
          </Sheet>
          <div className="flex-1">
            <h1 className="text-lg font-semibold">IoT Device Dashboard</h1>
          </div>
        </header>

        {/* Main Layout: Sidebar + Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Right Main Content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Top Section: Detected Tags + Control Buttons */}
            <div className="border-b bg-background p-4">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Detected Tags Panel */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Detected Tags</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div className="space-y-1">
                        <div className="text-2xl font-bold text-primary">{detectedTags}</div>
                        <div className="text-xs text-muted-foreground">Detected</div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-2xl font-bold">{totalTags}</div>
                        <div className="text-xs text-muted-foreground">Total</div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-lg font-mono font-bold tracking-wider">{timer}</div>
                        <div className="text-xs text-muted-foreground">Timer</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Inventory Control */}
                <InventoryControl
                  isInventoryRunning={isInventoryRunning}
                  isConnected={isConnected}
                  onStart={handleStartInventory}
                  onStop={handleStopInventory}
                  onClear={handleClear}
                />
              </div>
            </div>

            {/* Bottom Section: Tags Table */}
            <div className="flex-1 p-4 overflow-auto">
              {tags.length === 0 ? (
                <div className="text-center text-muted py-8">
                  Chưa có tags được phát hiện
                </div>
              ) : (
                <TagTable tags={tags} />
              )}
            </div>
          </div>
        </div>

        {/* Mobile Main Content */}
        <main className="flex-1 overflow-auto p-4 lg:hidden">
          <div className="space-y-4">
            {/* Detected Tags + Control Buttons - Mobile */}
            <div className="grid grid-cols-1 gap-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg">Detected Tags</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div className="space-y-1">
                      <div className="text-2xl font-bold text-primary">{detectedTags}</div>
                      <div className="text-xs text-muted-foreground">Detected</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-2xl font-bold">{totalTags}</div>
                      <div className="text-xs text-muted-foreground">Total</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-lg font-mono font-bold tracking-wider">{timer}</div>
                      <div className="text-xs text-muted-foreground">Timer</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <InventoryControl
                isInventoryRunning={isInventoryRunning}
                isConnected={isConnected}
                onStart={handleStartInventory}
                onStop={handleStopInventory}
                onClear={handleClear}
              />
            </div>
            {/* Tags Table - Mobile */}
            {tags.length === 0 ? (
              <div className="text-center text-muted py-8">
                Chưa có tags được phát hiện
              </div>
            ) : (
              <TagTable tags={tags} mobile />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
