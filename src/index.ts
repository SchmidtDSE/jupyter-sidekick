import {
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import { ILauncher } from '@jupyterlab/launcher';
import { LabIcon } from '@jupyterlab/ui-components';

import { AcpChatPanel } from './widget';

const OPEN = 'jupyter-sidekick:open';
const NEW = 'jupyter-sidekick:new-chat';

// Inlined (rather than importing a .svg module) so the production labextension
// build's license-webpack-plugin doesn't choke on an asset module.
const ACP_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16">
  <g class="jp-icon3" fill="#616161">
    <path d="M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10l-5 4v-4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>
  </g>
  <g fill="none" stroke="var(--jp-layout-color1, #fff)" stroke-width="1.6" stroke-linecap="round">
    <path d="M8 8.5h8M8 11.5h5"/>
  </g>
</svg>`;

export const acpIcon = new LabIcon({
  name: 'jupyter-sidekick:icon',
  svgstr: ACP_ICON_SVG
});

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyter-sidekick:plugin',
  description: 'Zed-style ACP chat for JupyterLab.',
  autoStart: true,
  optional: [ICommandPalette, ILauncher, ILayoutRestorer],
  activate: (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    launcher: ILauncher | null,
    restorer: ILayoutRestorer | null
  ) => {
    // One persistent chat docked in the left sidebar (icon-only). Drag the
    // tab to the right via right-click → "Switch Sidebar Side".
    let sidebar: AcpChatPanel | null = null;
    const ensureSidebar = (): AcpChatPanel => {
      if (sidebar === null || sidebar.isDisposed) {
        sidebar = new AcpChatPanel();
        sidebar.id = 'jupyter-sidekick-sidebar';
        sidebar.title.icon = acpIcon;
        sidebar.title.caption = 'ACP Chat'; // tooltip only — no text label
        app.shell.add(sidebar, 'left', { rank: 900 });
        if (restorer) {
          restorer.add(sidebar, 'jupyter-sidekick-sidebar');
        }
      }
      return sidebar;
    };

    // Additional chats open as main-area tabs: multiple at once, freely
    // draggable/splittable, with the file browser still docked.
    let counter = 0;
    const newMainChat = (): void => {
      counter += 1;
      const panel = new AcpChatPanel();
      panel.id = `jupyter-sidekick-chat-${Date.now()}-${counter}`;
      panel.title.icon = acpIcon;
      panel.title.label = `ACP Chat ${counter}`;
      panel.title.closable = true;
      app.shell.add(panel, 'main');
      app.shell.activateById(panel.id);
    };

    ensureSidebar();

    app.commands.addCommand(OPEN, {
      label: 'ACP Chat (sidebar)',
      caption: 'Reveal the docked ACP chat panel',
      icon: acpIcon,
      execute: () => app.shell.activateById(ensureSidebar().id)
    });
    app.commands.addCommand(NEW, {
      label: 'New ACP Chat',
      caption: 'Open a new ACP chat in the main area',
      icon: acpIcon,
      execute: () => newMainChat()
    });

    if (palette) {
      palette.addItem({ command: NEW, category: 'AI' });
      palette.addItem({ command: OPEN, category: 'AI' });
    }
    if (launcher) {
      launcher.add({ command: NEW, category: 'Other', rank: 1 });
    }
  }
};

export default plugin;
