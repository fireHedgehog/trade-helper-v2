import { useCallback, useEffect, useState, type ReactNode } from "react";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import type { Page } from "../types";

export interface Column<T> {
  key: string;
  label: string;
  align?: "left" | "right";
  render?: (row: T) => ReactNode;
}

interface ServerTableProps<T> {
  columns: Column<T>[];
  fetcher: (page: number, pageSize: number) => Promise<Page<T>>;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** Bump to force a refetch (e.g. after a fetch run completes). */
  refreshKey?: number;
  initialPageSize?: number;
  dense?: boolean;
}

export function ServerTable<T>({
  columns,
  fetcher,
  rowKey,
  onRowClick,
  refreshKey = 0,
  initialPageSize = 50,
  dense = true,
}: ServerTableProps<T>) {
  const [page, setPage] = useState(0); // 0-based for MUI
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [data, setData] = useState<Page<T> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetcher(page + 1, pageSize));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [fetcher, page, pageSize]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <Box>
      <Box sx={{ height: 3 }}>{loading && <LinearProgress />}</Box>
      <TableContainer sx={{ maxHeight: 460, overflowX: "auto" }}>
        <Table size={dense ? "small" : "medium"} stickyHeader>
          <TableHead>
            <TableRow>
              {columns.map((c) => (
                <TableCell key={c.key} align={c.align ?? "left"}>
                  {c.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.rows.map((row) => (
              <TableRow
                key={rowKey(row)}
                hover={!!onRowClick}
                onClick={() => onRowClick?.(row)}
                sx={{ cursor: onRowClick ? "pointer" : "default" }}
              >
                {columns.map((c) => (
                  <TableCell key={c.key} align={c.align ?? "left"}>
                    {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "")}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {data && data.rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={columns.length}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                    {error ?? "No data yet."}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={data?.total ?? 0}
        page={page}
        onPageChange={(_, p) => setPage(p)}
        rowsPerPage={pageSize}
        onRowsPerPageChange={(e) => {
          setPageSize(parseInt(e.target.value, 10));
          setPage(0);
        }}
        rowsPerPageOptions={[25, 50, 100, 200]}
      />
    </Box>
  );
}
