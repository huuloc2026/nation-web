import { useState, useEffect, useRef } from "react"
import { Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { Sidebar } from "./components/Sidebar"
import { TagTable } from "./components/TagTable"
import { connectReader, disconnectReader, startInventory, stopInventory, WriteEPCtag } from "./api/rfid"
import { toast } from "sonner"
import { io, Socket } from "socket.io-client"

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { InventoryControl } from "./components/InventoryControl"
import { TableWriteTag } from "./components/TableWriteTag"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@radix-ui/react-label"

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
  const [serialPort, setSerialPort] = useState("/dev/ttyUSB1")
  const [baudRate, setBaudRate] = useState("115200")
  const [detectedTags, setDetectedTags] = useState(0)
  const [totalTags, setTotalTags] = useState(0)
  const [timer, setTimer] = useState("00:00:00")
  const [isInventoryRunning, setIsInventoryRunning] = useState(false)
  const [tags, setTags] = useState<Tag[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)

  const [tableWriteTag, setTableWriteTag] = useState<boolean>(true)
  const [writeDialogOpen, setWriteDialogOpen] = useState(false)
  const [epcInput, setEpcInput] = useState("")
  const [writeParams, setWriteParams] = useState<any>(null)
  const [writeResult, setWriteResult] = useState<any>(null)
  const [writeLoading, setWriteLoading] = useState(false)

  // Antenna settings
  const [antennaSettings, setAntennaSettings] = useState<AntennaSettings>({
    antenna1: true,
    antenna2: false,
    antenna3: false,
    antenna4: false,
  })

  // --- WebSocket state ---
  const socketRef = useRef<Socket | null>(null)
  const tagMapRef = useRef<Map<string, Tag>>(new Map())

  // --- WebSocket setup ---
  useEffect(() => {
    // Connect to backend Socket.IO server
    const socket = io(import.meta.env.VITE_WS_URL ?? "http://localhost:3000", {
      transports: ["websocket"],   // force pure WS (optional)
      path: "/socket.io",          // match server if you changed it
      withCredentials: false,      // change to true if you **need** cookies
    })
    
    socketRef.current = socket
    socket.on("connect", () => console.log("🔌 Socket connected:", socket.id))
    socket.on("disconnect", (r) => console.warn("⚠️  disconnected:", r))
    socket.on("connect_error", (err) => console.error("❌ connect_error", err.message))

    // Handle tag_detected event
    socket.on("tag_detected", (tagData: any) => {
      // Update tagMapRef (aggregate by EPC)

      console.log(`Tag detected: ${tagData.epc}, RSSI: ${tagData.rssi}, Antenna: ${tagData.antenna}`)
      const tagMap = tagMapRef.current
      const epc = tagData.epc
      if (tagMap.has(epc)) {
        const existing = tagMap.get(epc)!
        existing.count += 1
        existing.lastSeen = tagData.timestamp
        if (tagData.rssi > existing.rssi) existing.rssi = tagData.rssi
        if (!`${existing.antenna}`.includes(`${tagData.antenna}`)) {
          existing.antenna = `${existing.antenna}, ${tagData.antenna}`
        }
      } else {
        tagMap.set(epc, {
          id: tagMap.size + 1,
          epc,
          count: 1,
          antenna: tagData.antenna,
          rssi: tagData.rssi,
          lastSeen: tagData.timestamp,
        })
      }
      // Update state
      const arr = Array.from(tagMap.values())
      setTags(arr)
      setDetectedTags(arr.length)
      setTotalTags(arr.reduce((sum, t) => sum + t.count, 0))
    })

    // Optionally handle inventory_end event
    socket.on("inventory_end", () => {
      // You may want to stop inventory or show a message
      setIsInventoryRunning(false)
    })

    return () => {
      socket.disconnect()
      socketRef.current = null
    }
  }, [])

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

  // --- Clear tags on inventory start/stop ---
  const handleStartInventory = async () => {
    tagMapRef.current.clear()
    setTags([])
    setDetectedTags(0)
    setTotalTags(0)
    setIsInventoryRunning(true)
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

  const handleClear = async () => {
    tagMapRef.current.clear()
    setTags([])
    setDetectedTags(0)
    setTotalTags(0)
    setTimer("00:00:00")
    setElapsedMs(0)
    setIsInventoryRunning(false)
  }

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

  const handleWriteEPC = async () => {
    setWriteDialogOpen(true)
    setEpcInput("")
    setWriteParams(null)
    setWriteResult(null)
  }

  const handleSubmitWrite = async () => {
    if (!epcInput.trim()) {
      toast("EPC không được để trống", { style: { background: "#ef4444", color: "#fff" } })
      return
    }
    setWriteLoading(true)
    // Example: always use antenna 1, EPC area, start word 2
    const params = {
      antennaMask: 1,
      dataArea: 1,
      startWord: 2,
      epcHex: epcInput.trim().toUpperCase(),
    }
    setWriteParams(params)
    // TODO: Call actual API to write EPC and get result
    // call writeEPC(params)
    // For demo purposes, we simulate a successful write after 1.2 seconds
    // You can replace this with actual API call logic
   
    const data = await WriteEPCtag(params.antennaMask, params.dataArea, params.startWord, params.epcHex)
    console.log("Write EPC result:", data)  

    
    // Simulate result for demo


    setTimeout(() => {
      setWriteResult({
        success: true,
        result_code: 0,
        result_msg: "Write successfully",
        failed_addr: null,
      })

      toast("Ghi EPC thành công", {
        description: "EPC đã được ghi vào tag",
      })
      setWriteDialogOpen(false) // Close dialog after success

      setWriteLoading(false)
    }, 1200)
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
          setAntennaSettings={setAntennaSettings}
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
            setAntennaSettings={setAntennaSettings}
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
                  writeEPC={handleWriteEPC}
                />
              </div>
            </div>

            {/* Bottom Section: Tags Table */}
            <div className="flex-1 p-4 overflow-auto">
              {tags.length === 0 ? (
                <div className="text-center text-muted-foreground py-8">
                  No EPC tags detected
                </div>
              ) : (
                <TagTable tags={tags} />
              )}
            </div>

            {/* Write EPC Dialog */}
            <Dialog open={writeDialogOpen} onOpenChange={setWriteDialogOpen}>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Ghi EPC vào Tag</DialogTitle>
                </DialogHeader>
                <DialogDescription>
        
           </DialogDescription>
                <div className="space-y-2">
                  <Label htmlFor="epc-input">EPC </Label>
                  <Input
                    id="epc-input"
                    value={epcInput}
                    onChange={e => setEpcInput(e.target.value)}
                    placeholder="EPC"
                    disabled={writeLoading}
                    autoFocus
                  />
                </div>
                <DialogFooter>
                  <Button onClick={handleSubmitWrite} disabled={writeLoading || !epcInput.trim()}>
                    {writeLoading ? "Đang ghi..." : "Ghi EPC"}
                  </Button>
                  <Button variant="outline" onClick={() => setWriteDialogOpen(false)} disabled={writeLoading}>
                    Đóng
                  </Button>
                </DialogFooter>
                {(writeParams || writeResult) && (
                  <div className="mt-4">
                    <TableWriteTag params={writeParams || {}} result={writeResult} />
                  </div>
                )}
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>
    </div>
  )
}
