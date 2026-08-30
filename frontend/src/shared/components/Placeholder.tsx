import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

interface PlaceholderProps {
  title: string;
  subtitle: string;
}

export function Placeholder({ title, subtitle }: PlaceholderProps) {
  return (
    <div>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        {subtitle}
      </Typography>
      <Paper sx={{ p: 3 }}>
        <Typography color="text.secondary">This page is not implemented yet.</Typography>
      </Paper>
    </div>
  );
}
