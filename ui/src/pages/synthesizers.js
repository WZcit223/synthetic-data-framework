// The Synthesizers page's entry module: mounts the page component (interfaces.md §1.3).
import { mount } from "svelte";

import "../theme.css";
import "../app.css";
import Synthesizers from "./Synthesizers.svelte";

mount(Synthesizers, { target: document.getElementById("app") });
