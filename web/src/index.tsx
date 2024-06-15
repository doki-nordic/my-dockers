
import { Section, Alignment, Button, ContextMenu, Dialog, DialogBody, DialogFooter, Icon, InputGroup, Intent, Menu, MenuDivider, MenuItem, Navbar, OverlayToaster, Popover, Spinner, Tab, TabId, Tabs, Toaster, SectionCard, EntityTitle, H1, H3, H2, Elevation, ButtonGroup, NavbarGroup, IconSize, Tag, Tree, Tooltip } from '@blueprintjs/core';
import React, { useCallback } from 'react';
import ReactDOM from 'react-dom';

import 'normalize.css/normalize.css';
import '@blueprintjs/core/lib/css/blueprint.css';
import '@blueprintjs/icons/lib/css/blueprint-icons.css';

interface State {
    test: boolean;
};

const initialState: State = {
    test: false,
};


let stateCurrent: State | undefined = undefined;
let stateTemp: State | undefined = undefined;
let setStateOriginal: React.Dispatch<React.SetStateAction<State>>;

function setState(state: State) {
    if (stateTemp) {
        if (state === stateTemp) return; // ignore - this is recently set state
    } else {
        if (state === stateCurrent) return; // ignore - this is current state
    }
    stateTemp = state;
    setStateOriginal(state);
}

function getState(): State {
    if (!stateCurrent) {
        throw new Error('State not ready');
    }
    return stateTemp || stateCurrent;
}


function App() {
    let [state, setStateFromReact] = React.useState<State>({ ...initialState });
    setStateOriginal = setStateFromReact;
    stateCurrent = state;
    stateTemp = undefined;
    return (
        <>
            <Section compact={true} icon={<Icon icon="box" size={IconSize.LARGE} />} title="ncs / ncs" subtitle={<small style={{ color: '#FF9080' }}>Out of date</small>} collapsible={true} elevation={Elevation.ONE}
                rightElement={
                    <ButtonGroup>
                        <Button icon="build" text="Build" onClick={(event: React.MouseEvent) => { event.stopPropagation(); }} />
                        <Button icon="trash" text="Remove" onClick={(event: React.MouseEvent) => { event.stopPropagation(); }} />
                    </ButtonGroup>
                }
            >
                <SectionCard>
                    <div style={{fontSize: "80%", color: '#808080'}}>This is some description of the docker file.</div>
                </SectionCard>
                <SectionCard padded={true}>
                    <div className='command'>
                        <div />
                        <div><Icon icon="console" size={IconSize.LARGE} /></div>
                        <div>
                            <EntityTitle title="ncs" heading={H2} subtitle={
                                <>
                                    <Popover content={
                                        <Menu>
                                            <MenuItem icon="play" onClick={() => { }} text="Resume" />
                                            <MenuItem icon="pause" onClick={() => { }} text="Pause" disabled={true} />
                                            <MenuItem icon="trash" onClick={() => { }} text="Dispose" />
                                        </Menu>
                                    }><Tag minimal={true} interactive={true}>Paused</Tag></Popover>&nbsp;&nbsp;

                                    <Popover content={
                                        <Menu>
                                        <MenuItem icon="trash" onClick={() => { }} text="Dispose" />
                                        </Menu>
                                    }><Tooltip content={<div style={{maxWidth: 250}}>
                                        The container is <b>not</b> running on the latest image build.
                                        You have to <b>dispose</b> it first before using the latest image.
                                        </div>}>
                                    <Tag minimal={true} interactive={true} intent={Intent.DANGER}>Outdated</Tag>&nbsp;&nbsp;
                                    </Tooltip></Popover>
                                </>
                            } />
                        </div>
                        <div>
                        <Button icon="console" text="Terminal" onClick={(event: React.MouseEvent) => { event.stopPropagation(); }} />
                        </div>
                    </div>
                    <div style={{ marginLeft: 40, marginTop: 14 }}>
                        <Tree contents={[
                            {
                                id: "one", label: "/home/doki/work", icon: "folder-close", secondaryLabel: (
                                    <ButtonGroup>
                                        <Button small={true} minimal={true} icon="trash" onClick={(event: React.MouseEvent) => { event.stopPropagation(); }} />
                                    </ButtonGroup>
                                )
                            },
                            {
                                id: "two", label: "/home/doki/my", icon: "folder-close", secondaryLabel: (
                                    <Button small={true} minimal={true} icon="trash" onClick={(event: React.MouseEvent) => { event.stopPropagation(); }} />
                                )
                            },
                            {
                                id: "aa", label: (<InputGroup small={true} />), icon: "folder-new", secondaryLabel: (
                                    <Button small={true} minimal={true} icon="tick" text="Add" onClick={(event: React.MouseEvent) => { event.stopPropagation(); }} />
                                )
                            },
                        ]}></Tree>
                    </div>
                </SectionCard>
                <SectionCard>

                    <div className='command'>
                        <div />
                        <div><Icon icon="console" size={IconSize.LARGE} /></div>
                        <div><InputGroup large={true} /></div>
                        <div>
                            <Button large={true} minimal={true} icon="tick" text="Add" onClick={(event: React.MouseEvent) => { event.stopPropagation(); }} />
                        </div>
                    </div>
                </SectionCard>
            </Section >
        </>
    );
}

window.onload = async () => {
    //mainToaster = await OverlayToaster.createAsync({ position: 'top' });
    ReactDOM.render(<App />, document.getElementById('reactRoot'));
};
