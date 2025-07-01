import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

interface WriteTagParam {
  antennaMask: number
  dataArea: number
  startWord: number
  epcHex: string
  matchArea?: number
  matchStart?: number
  matchBitLen?: number
  matchData?: string
  accessPwd?: string
  blockWrite?: number
}

interface WriteTagResult {
  success: boolean
  result_code: number
  result_msg: string
  failed_addr?: number | null
}

interface TableWriteTagProps {
  params: WriteTagParam
  result?: WriteTagResult
}

export function TableWriteTag({ params, result }: TableWriteTagProps) {
  // Map for Data Area
  const areaMap: Record<number, string> = {
    0: "Reserve",
    1: "EPC",
    2: "TID",
    3: "User",
  }
  // Map for result code
  const codeMap: Record<number, string> = {
    0: "Write successfully",
    1: "Antenna port parameter error",
    2: "Choosing parameter error",
    3: "Writing parameter error",
    4: "CRC check error",
    5: "Insufficient power",
    6: "Data area overflow",
    7: "Data area locked",
    8: "Access password error",
    9: "Other tag errors",
    10: "Tag lost",
    11: "Reader sending command error",
  }

  return (
    <div className="rounded-md border mb-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead colSpan={3} className="text-center">Write EPC Tag Parameters</TableHead>
          </TableRow>
          <TableRow>
            <TableHead>Parameter</TableHead>
            <TableHead>Value</TableHead>
            <TableHead>Description</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Antenna Port</TableCell>
            <TableCell>
              {params.antennaMask} (0x{params.antennaMask.toString(16).toUpperCase().padStart(8, "0")})
            </TableCell>
            <TableCell>Bitmask, Bit0=Ant1</TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Data Area</TableCell>
            <TableCell>{params.dataArea}</TableCell>
            <TableCell>{areaMap[params.dataArea] || "Unknown"}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Word Start Addr</TableCell>
            <TableCell>{params.startWord}</TableCell>
            <TableCell>Start word in area</TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Data Content</TableCell>
            <TableCell>{params.epcHex}</TableCell>
            <TableCell>EPC to write</TableCell>
          </TableRow>
          {params.matchArea !== undefined && (
            <TableRow>
              <TableCell>Match Parameter (PID 0x01)</TableCell>
              <TableCell>
                Area: {params.matchArea}, Start: {params.matchStart}, BitLen: {params.matchBitLen}, Data: {params.matchData}
              </TableCell>
              <TableCell>Optional: Match before write</TableCell>
            </TableRow>
          )}
          {params.accessPwd && (
            <TableRow>
              <TableCell>Access Password (PID 0x02)</TableCell>
              <TableCell>{params.accessPwd}</TableCell>
              <TableCell>Optional: Tag access password</TableCell>
            </TableRow>
          )}
          {params.blockWrite !== undefined && (
            <TableRow>
              <TableCell>Block Write Param (PID 0x03)</TableCell>
              <TableCell>{params.blockWrite}</TableCell>
              <TableCell>Optional: Block write word length</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {result && (
        <Table className="mt-4">
          <TableHeader>
            <TableRow>
              <TableHead colSpan={4} className="text-center">Write EPC Tag Result</TableHead>
            </TableRow>
            <TableRow>
              <TableHead>Result</TableHead>
              <TableHead>Result Code</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Failed Word Addr</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>{result.success ? "✅" : "❌"}</TableCell>
              <TableCell>{result.result_code}</TableCell>
              <TableCell>{codeMap[result.result_code] || result.result_msg}</TableCell>
              <TableCell>
                {result.failed_addr !== undefined && result.failed_addr !== null ? result.failed_addr : "-"}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )}
    </div>
  )
}
