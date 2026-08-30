import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import type { Page } from "../types";
import { ServerTable, type Column } from "./ServerTable";

interface DetailDialogProps<T> {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Header key/value block (all columns of the parent row). */
  header: Record<string, unknown> | null;
  columns: Column<T>[];
  fetcher: (page: number, pageSize: number) => Promise<Page<T>>;
  rowKey: (row: T) => string;
}

export function DetailDialog<T>({
  open,
  onClose,
  title,
  header,
  columns,
  fetcher,
  rowKey,
}: DetailDialogProps<T>) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>
        {title}
        <IconButton onClick={onClose} sx={{ position: "absolute", right: 8, top: 8 }}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {header && (
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: 1,
              mb: 2,
            }}
          >
            {Object.entries(header).map(([k, v]) => (
              <Box key={k}>
                <Typography variant="caption" color="text.secondary">
                  {k}
                </Typography>
                <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
                  {v === null || v === undefined || v === "" ? "—" : String(v)}
                </Typography>
              </Box>
            ))}
          </Box>
        )}
        {open && (
          <ServerTable
            columns={columns}
            fetcher={fetcher}
            rowKey={rowKey}
            initialPageSize={100}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
