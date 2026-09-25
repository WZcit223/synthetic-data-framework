// The Effects page's entry module: mounts the page component (interfaces.md §1.3).
import { mount } from "svelte";

import "../theme.css";
import "../app.css";
import Effects from "./Effects.svelte";

mount(Effects, { target: document.getElementById("app") });
