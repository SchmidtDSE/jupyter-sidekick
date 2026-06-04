import {
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import { ILauncher } from '@jupyterlab/launcher';
import { LabIcon } from '@jupyterlab/ui-components';

import acpSvgStr from '../style/icons/acp.svg';
import { AcpChatPanel } from './widget';

const COMMAND = 'jupyter-acp:open';

export const acpIcon = new LabIcon({
  name: 'jupyter-acp:icon',
  svgstr: acpSvgStr
});

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyter-acp:plugin',
  description: 'Zed-style ACP chat for JupyterLab.',
  autoStart: true,
  optional: [ICommandPalette, ILauncher, ILayoutRestorer],
  activate: (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    launcher: ILauncher | null,
    restorer: ILayoutRestorer | null
  ) => {
    // A single persistent panel in the left sidebar (drag to the right sidebar
    // if preferred — JupyterLab supports moving side panels).
    const panel = new AcpChatPanel();
    panel.id = 'jupyter-acp-panel';
    panel.title.icon = acpIcon;
    panel.title.caption = 'ACP Chat';
    app.shell.add(panel, 'left', { rank: 900 });
    if (restorer) {
      restorer.add(panel, 'jupyter-acp-panel');
    }

    app.commands.addCommand(COMMAND, {
      label: 'ACP Chat',
      caption: 'Open the ACP chat panel',
      icon: acpIcon,
      execute: () => {
        app.shell.activateById(panel.id);
      }
    });

    if (palette) {
      palette.addItem({ command: COMMAND, category: 'AI' });
    }
    if (launcher) {
      launcher.add({ command: COMMAND, category: 'Other', rank: 1 });
    }
  }
};

export default plugin;
