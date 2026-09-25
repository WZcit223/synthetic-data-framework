// The Explore page's entry module: mounts the page component (interfaces.md §1.3).
import { mount } from "svelte";

import "../theme.css";
import "../app.css";
import Explore from "./Explore.svelte";

mount(Explore, { target: document.getElementById("app") });
