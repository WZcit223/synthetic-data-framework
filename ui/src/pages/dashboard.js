// The dashboard's entry module: mounts the page component (interfaces.md §1.3).
import { mount } from "svelte";

import "../theme.css";
import "../app.css";
import Dashboard from "./Dashboard.svelte";

mount(Dashboard, { target: document.getElementById("app") });
