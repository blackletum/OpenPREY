// Copyright (C) 2026 DarkMatter Productions
// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef OPENPR06_OBITUARY_WINDOW_H
#define OPENPR06_OBITUARY_WINDOW_H

#include "Window.h"

/*
openPR06: the graphical obituary feed, "obituaryDef" in a GUI script
(guis/obituaries.gui). The game hands each death over once, through GUI
state and the "obitPush" named event:

	obit_killer, obit_victim	names; an empty killer draws the icon before the victim alone
	obit_icon, obit_badge		material names: the weapon (or skull, telefrag, generic) and
								an optional corner badge (alternate fire, suicide)
	obit_killerTeam,			-1 without teams, 0 blue, 1 red
	obit_victimTeam
	obit_self					1 the local player killed, 2 the local player died
	obit_time					the game time of the death; the GUI's time if absent

"obitReset" empties the feed. Each line lives "lifetime" ms (3000), at most
"maxlines" (5) at once; a line arriving at a full feed hurries the oldest
out. Layout, timing and palette: docs/dev/prey-ui-visual-design.md, 12.1.
*/
class idObituaryWindow : public idWindow {
public:
	idObituaryWindow( idDeviceContext *dc, idUserInterfaceLocal *gui );

	void				Draw( int time, float x, float y ) override;
	void				RunNamedEvent( const char *eventName ) override;

protected:
	bool				ParseInternalVar( const char *name, idParser *src ) override;

private:
	static const int	MAX_LINES = 8;

	struct line_t {
		idStr				killer;
		idStr				victim;
		const idMaterial *	icon;
		const idMaterial *	badge;
		idVec4				killerInk;
		idVec4				victimInk;
		int					self;
		int					start;
		int					end;
		float				y;					// drawn offset from the feed's top, eased toward its slot
		// measured on the first draw, again when the type scale changes
		float				measuredScale;
		float				killerWidth;
		float				victimWidth;
		float				iconWidth;
	};

	void				Clear();
	void				Push( int now );
	void				Measure( line_t &line, float scale );
	void				Truncate( idStr &name, float scale, float limit );
	void				DrawLine( const line_t &line, float left, float top, int time );

	line_t				lines[ MAX_LINES ];
	int					numLines;
	int					maxLines;
	int					lifeTime;
	int					lastDrawTime;
};

#endif
