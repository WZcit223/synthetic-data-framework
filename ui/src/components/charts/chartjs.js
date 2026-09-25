// Chart.js, with only the parts the chart components use registered once.
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  ScatterController,
  Tooltip,
} from "chart.js";
import { PointWithErrorBar, ScatterWithErrorBarsController } from "chartjs-chart-error-bars";
import { MatrixController, MatrixElement } from "chartjs-chart-matrix";

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  ScatterController,
  Tooltip,
  ScatterWithErrorBarsController,
  PointWithErrorBar,
  MatrixController,
  MatrixElement,
);

export { Chart };
