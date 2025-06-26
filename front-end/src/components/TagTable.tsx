import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { Tag } from "../App"

interface TagTableProps {
  tags: Tag[]
  mobile?: boolean
}

export function TagTable({ tags, mobile }: TagTableProps) {
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className={mobile ? "w-[150px]" : "w-[200px] sm:w-auto"}>EPC</TableHead>
            <TableHead className="text-center w-16">Count</TableHead>
            <TableHead className="text-center w-20">Antenna</TableHead>
            <TableHead className="text-center w-24">RSSI</TableHead>
            {!mobile && <TableHead className="hidden sm:table-cell">Last Seen</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {tags.length === 0 ? (
            <TableRow>
              <TableCell colSpan={mobile ? 4 : 5} className="text-center text-muted-foreground py-8">
                No tags detected. Start inventory to begin scanning.
              </TableCell>
            </TableRow>
          ) : (
            tags.map((tag) => (
              <TableRow key={tag.id}>
                <TableCell className={cn("font-mono text-xs", !mobile && "sm:text-sm")}>
                  <div className={cn("truncate", mobile ? "max-w-[120px]" : "max-w-[150px] sm:max-w-none")}>{tag.epc}</div>
                </TableCell>
                <TableCell className="text-center">
                  <Badge variant="secondary" className="text-xs">
                    {tag.count}
                  </Badge>
                </TableCell>
                <TableCell className="text-center text-sm">{tag.antenna}</TableCell>
                <TableCell className="text-center">
                  <span
                    className={cn(
                      "font-medium text-xs",
                      !mobile && "sm:text-sm",
                      tag.rssi > -50
                        ? "text-green-600"
                        : tag.rssi > -60
                          ? "text-yellow-600"
                          : "text-red-600",
                    )}
                  >
                    {tag.rssi}
                  </span>
                </TableCell>
                {!mobile && (
                  <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                    {tag.lastSeen}
                  </TableCell>
                )}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
