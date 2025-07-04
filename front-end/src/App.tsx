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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { BAUD_RATE_OPTIONS, SERIPORT, SOCKET_URL } from "./utils/constant"

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
  const [serialPort, setSerialPort] = useState(SERIPORT)
  const [baudRate, setBaudRate] = useState(BAUD_RATE_OPTIONS)
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
  const [detectedEPCs, setDetectedEPCs] = useState<string[]>([])
  const [selectedEPC, setSelectedEPC] = useState<string>("")
  const [epcScanLoading, setEpcScanLoading] = useState(false)
  const [selectedAntennas, setSelectedAntennas] = useState<number[]>([1])
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


  useEffect(() => {
    const socket = io(SOCKET_URL, {
      transports: ["websocket"],
      path: "/socket.io",
      withCredentials: false,
    });
  
    socketRef.current = socket;
  
    const handleTagDetected = (tagData: any) => {
      const map = tagMapRef.current;
      const { epc } = tagData;
      if (map.has(epc)) {
        const t = map.get(epc)!;
        t.count += 1;
        t.lastSeen = tagData.timestamp;
        t.rssi = Math.max(t.rssi, tagData.rssi);
        const antennas = new Set(
          `${t.antenna}`.split(",").map(a=>a.trim()).filter(Boolean)
        );
        antennas.add(String(tagData.antenna));
        t.antenna = Array.from(antennas).join(", ");
      } else {
        map.set(epc, {
          id: map.size + 1,
          epc,
          count: 1,
          antenna: tagData.antenna,
          rssi: tagData.rssi,
          lastSeen: tagData.timestamp,
        });
      }
      const arr = Array.from(map.values());
      setTags(arr);
      setDetectedTags(arr.length);
      setTotalTags(arr.reduce((s, t) => s + t.count, 0));
    };
  
    socket.on("tag_detected", handleTagDetected);
    socket.on("inventory_end", () => setIsInventoryRunning(false));
  
    return () => {
      socket.off("tag_detected", handleTagDetected); 
      socket.disconnect();                           
      socketRef.current = null;
    };
  }, []);
  

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
    await startInventory(selectedAntennas)
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
    setDetectedEPCs([])
    setSelectedEPC("")
    setEpcScanLoading(true)
    try {
      await startInventory(selectedAntennas)
      setTimeout(async () => {
        await stopInventory()
        // Use fetch directly for /api/get_tags as there is no apiCall for this
        const res = await startInventory(selectedAntennas)
        const data = await res.json()
        const epcs = Array.isArray(data.data) ? Array.from(new Set(data.data.map((t: any) => String(t.epc)))) as string[] : []
        setDetectedEPCs(epcs)
        setSelectedEPC(typeof epcs[0] === "string" ? epcs[0] : "")
        setEpcScanLoading(false)
      }, 2000)
    } catch (e) {
      setEpcScanLoading(false)
      setDetectedEPCs([])
    }
  }

  const handleSubmitWrite = async () => {
    if (!epcInput.trim() || !selectedEPC) {
      toast("Vui lòng chọn EPC và nhập EPC mới", { style: { background: "#ef4444", color: "#fff" } })
      return
    }
    setWriteLoading(true)
    const params = {
      antennaMask: 1,
      dataArea: 1,
      startWord: 2,
      epcHex: epcInput.trim().toUpperCase(),
    }
    setWriteParams(params)
    try {
      // Use WriteEPCtag from rfid.ts
      const data = await WriteEPCtag(
        params.antennaMask,
        params.dataArea,
        params.startWord,
        params.epcHex,
        selectedEPC,
        undefined,
        2.0
      )
      setWriteResult({
        success: data.success,
        result_code: data.result_code ?? (data.success ? 0 : -1),
        result_msg: data.result_msg || data.message || (data.success ? "Write successfully" : "Write failed"),
        failed_addr: data.failed_addr ?? null,
      })
      if (data.success) {
        toast("Ghi EPC thành công", { description: "EPC đã được ghi vào tag" })
        setWriteDialogOpen(false)
      } else {
        toast("Ghi EPC thất bại", { description: data.result_msg || data.message || "Write failed", style: { background: "#ef4444", color: "#fff" } })
      }
    } catch (e: any) {
      setWriteResult({
        success: false,
        result_code: -99,
        result_msg: e?.message || "Exception",
        failed_addr: null,
      })
      toast("Không thể ghi EPC tag.", { description: "Lỗi", style: { background: "#ef4444", color: "#fff" } })
    }
    setWriteLoading(false)
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
          onSetAntenna={(ants: number[]) => setSelectedAntennas(ants)}
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
            onSetAntenna={(ants: number[]) => setSelectedAntennas(ants)}
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
            <h1 className="text-lg font-semibold">Nation Dashboard</h1>
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
                  {epcScanLoading ? (
                    <div className="text-center py-4">Đang quét thẻ... Vui lòng chờ 2 giây.</div>
                  ) : (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="epc-select">Chọn EPC hiện tại</Label>
                        <Select
                          value={selectedEPC}
                          onValueChange={setSelectedEPC}
                          disabled={epcScanLoading || detectedEPCs.length === 0}
                        >
                          <SelectTrigger id="epc-select" className="w-full">
                            <SelectValue placeholder="Chọn EPC" />
                          </SelectTrigger>
                          <SelectContent>
                            {detectedEPCs.length === 0 ? (
                              <SelectItem value="" disabled>
                                Không tìm thấy EPC nào
                              </SelectItem>
                            ) : (
                              detectedEPCs.map(epc => (
                                <SelectItem key={epc} value={epc}>
                                  {epc}
                                </SelectItem>
                              ))
                            )}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2 mt-2">
                        <Label htmlFor="epc-input">EPC mới</Label>
                        <Input
                          id="epc-input"
                          value={epcInput}
                          onChange={e => setEpcInput(e.target.value)}
                          placeholder="Nhập EPC mới"
                          disabled={writeLoading}
                          autoFocus
                        />
                      </div>
                    </>
                  )}
                </DialogDescription>
                <DialogFooter>
                  <Button
                    onClick={handleSubmitWrite}
                    disabled={writeLoading || epcScanLoading || !epcInput.trim() || !selectedEPC}
                  >
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
