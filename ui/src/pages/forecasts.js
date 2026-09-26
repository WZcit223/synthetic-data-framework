// The Forecasts page's entry module: mounts the page component (interfaces.md §1.3).
import { mount } from "svelte";

import "../theme.css";
import "../app.css";
import Forecasts from "./Forecasts.svelte";

mount(Forecasts, { target: document.getElementById("app") });
