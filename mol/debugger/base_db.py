import fnmatch
import sys
import os
import linecache
from mol.move_vm.runtime.trace_help import TraceType, TracableFrame, GlobalTracer


class BaseDebuggerQuit(Exception):
    """Exception to give up completely."""


class BaseDebugger:
    """Generic Python debugger base class.

    This class takes care of details of the trace facility;
    a derived class should implement user interaction.
    The standard debugger class (pdb.Pdb) is an example.

    The optional skip argument must be an iterable of glob-style
    module name patterns.  The debugger will not step into frames
    that originate in a module that matches one of these patterns.
    Whether a frame is considered to originate in a certain module
    is determined by the __name__ in the frame globals.
    """

    def __init__(self, move=True, skip=None):
        self.skip = set(skip) if skip else None
        self.breaks = {}
        self.fncache = {}
        self.frame_returning = None

    def canonic(self, filename):
        """Return canonical form of filename.

        For real filenames, the canonical form is a case-normalized (on
        case insensitive filesystems) absolute path.  'Filenames' with
        angle brackets, such as "<stdin>", generated in interactive
        mode, are returned unchanged.
        """
        if filename is None:
            breakpoint()
        if filename == "<" + filename[1:-1] + ">":
            return filename
        canonic = self.fncache.get(filename)
        if not canonic:
            canonic = os.path.abspath(filename)
            canonic = os.path.normcase(canonic)
            self.fncache[filename] = canonic
        return canonic

    def reset(self):
        """Set values of attributes as ready to start debugging."""
        import linecache
        linecache.checkcache()
        self.botframe = None
        self._set_stopinfo(None, None)

    def trace_dispatch(self, frame, event, arg):
        """Dispatch a trace function for debugged frames based on the event.

        This function is installed as the trace function for debugged
        frames. Its return value is the new trace function, which is
        usually itself. The default implementation decides how to
        dispatch a frame, depending on the type of event (passed in as a
        string) that is about to be executed.

        The event can be one of the following:
            line: A new line of code is going to be executed.
            call: A function is about to be called or another code block
                  is entered.
            return: A function or other code block is about to return.
            exception: An exception has occurred.
            c_call: A C function is about to be called.
            c_return: A C function has returned.
            c_exception: A C function has raised an exception.

        For the Python events, specialized functions (see the dispatch_*()
        methods) are called.  For the C events, no action is taken.

        The arg parameter depends on the previous event.
        """
        if self.quitting:
            return # None
        if event == TraceType.LINE:
            return self.dispatch_line(frame)
        if event == TraceType.CALL:
            return self.dispatch_call(frame, arg)
        if event == TraceType.RETURN:
            return self.dispatch_return(frame, arg)
        if event == TraceType.EXCEPTION:
            return self.dispatch_exception(frame, arg)
        if event == TraceType.NATIVE_CALL:
            return self.trace_dispatch
        if event == TraceType.NATIVE_EXCEPTION:
            return self.trace_dispatch
        if event == TraceType.NATIVE_RETURN:
            return self.trace_dispatch
        print('bdb.BaseDebugger.dispatch: unknown debugging event:', repr(event))
        return self.trace_dispatch

    def dispatch_line(self, frame):
        """Invoke user function and return trace function for line event.

        If the debugger stops on the current line, invoke
        self.user_line(). Raise BaseDebuggerQuit if self.quitting is set.
        Return self.trace_dispatch to continue tracing in this scope.
        """
        if self.stop_here(frame) or self.break_here(frame):
            self.user_line(frame)
            if self.quitting: raise BaseDebuggerQuit
        return self.trace_dispatch

    def dispatch_call(self, frame, arg):
        """Invoke user function and return trace function for call event.

        If the debugger stops on this function call, invoke
        self.user_call(). Raise BbdQuit if self.quitting is set.
        Return self.trace_dispatch to continue tracing in this scope.
        """
        # XXX 'arg' is no longer used
        if self.botframe is None:
            # First call of dispatch since reset()
            self.botframe = frame.f_back or frame # (CT) Note that this may also be None!
            # return self.trace_dispatch
        if not (self.stop_here(frame) or self.break_anywhere(frame)):
            # No need to trace this function
            return # None
        self.user_call(frame, arg)
        if self.quitting: raise BaseDebuggerQuit
        return self.trace_dispatch

    def dispatch_return(self, frame, arg):
        """Invoke user function and return trace function for return event.

        If the debugger stops on this function return, invoke
        self.user_return(). Raise BaseDebuggerQuit if self.quitting is set.
        Return self.trace_dispatch to continue tracing in this scope.
        """
        if self.stop_here(frame) or frame == self.returnframe:
            try:
                self.frame_returning = frame
                self.user_return(frame, arg)
            finally:
                self.frame_returning = None
            if self.quitting: raise BaseDebuggerQuit
            # The user issued a 'next' or 'until' command.
            if self.stopframe is frame and self.stoplineno != -1:
                self._set_stopinfo(None, None)
        return self.trace_dispatch

    def dispatch_exception(self, frame, arg):
        """Invoke user function and return trace function for exception event.

        If the debugger stops on this exception, invoke
        self.user_exception(). Raise BaseDebuggerQuit if self.quitting is set.
        Return self.trace_dispatch to continue tracing in this scope.
        """
        if self.stop_here(frame):
            self.user_exception(frame, arg)
            if self.quitting: raise BaseDebuggerQuit

        return self.trace_dispatch

    # Normally derived classes don't override the following
    # methods, but they may if they want to redefine the
    # definition of stopping and breakpoints.

    def is_skipped_module(self, frame):
        "Return True if module_name matches any skip pattern."
        address, mname, fname = frame.address_module_function()
        for pattern in self.skip:
            if address == pattern or mname == pattern or fname == pattern:
                return True
        return False

    def stop_here(self, frame):
        "Return True if frame is below the starting frame in the stack."
        # (CT) stopframe may now also be None, see dispatch_call.
        # (CT) the former test for None is therefore removed from here.
        if self.skip and self.is_skipped_module(frame):
            return False
        if frame is self.stopframe:
            if self.stoplineno == -1:
                return False
            return frame.f_lineno >= self.stoplineno
        if not self.stopframe:
            return True
        return False

    def break_here(self, frame):
        """Return True if there is an _effective breakpoint for this line.

        Check for line or function breakpoint and if in effect.
        Delete temporary breakpoints if _effective() says to.
        """
        filename = self.canonic(frame.source_filename())
        if filename not in self.breaks:
            return False
        lineno = frame.f_lineno
        if lineno not in self.breaks[filename]:
            # The line itself has no breakpoint, but maybe the line is the
            # first line of a function with breakpoint set by function name.
            lineno = frame.frame_first_lineno()
            if lineno not in self.breaks[filename]:
                return False

        # flag says ok to delete temp. bp
        (bp, flag) = _effective(filename, lineno, frame)
        if bp:
            self.currentbp = bp.number
            if (flag and bp.temporary):
                self.do_clear(str(bp.number))
            return True
        else:
            return False

    def do_clear(self, arg):
        """Remove temporary breakpoint.

        Must implement in derived classes or get NotImplementedError.
        """
        raise NotImplementedError("subclass of bdb must implement do_clear()")

    def break_anywhere(self, frame):
        """Return True if there is any breakpoint for frame's filename.
        """
        return self.canonic(frame.source_filename()) in self.breaks

    # Derived classes should override the user_* methods
    # to gain control.

    def user_call(self, frame, argument_list):
        """Called if we might stop in a function."""
        pass

    def user_line(self, frame):
        """Called when we stop or break at a line."""
        pass

    def user_return(self, frame, return_value):
        """Called when a return trap is set here."""
        pass

    def user_exception(self, frame, exc_info):
        """Called when we stop on an exception."""
        pass

    def _set_stopinfo(self, stopframe, returnframe, stoplineno=0):
        """Set the attributes for stopping.

        If stoplineno is greater than or equal to 0, then stop at line
        greater than or equal to the stopline.  If stoplineno is -1, then
        don't stop at all.
        """
        self.stopframe = stopframe
        self.returnframe = returnframe
        self.quitting = False
        # stoplineno >= 0 means: stop at line >= the stoplineno
        # stoplineno -1 means: don't stop at all
        self.stoplineno = stoplineno

    # Derived classes and clients can call the following methods
    # to affect the stepping state.

    def set_until(self, frame, lineno=None):
        """Stop when the line with the lineno greater than the current one is
        reached or when returning from current frame."""
        # the name "until" is borrowed from gdb
        if lineno is None:
            lineno = frame.f_lineno + 1
        self._set_stopinfo(frame, frame, lineno)

    def set_step(self):
        """Stop after one line of code."""
        # Issue #13183: pdb skips frames after hitting a breakpoint and running
        # step commands.
        # Restore the trace function in the caller (that may not have been set
        # for performance reasons) when returning from the current frame.
        if self.frame_returning:
            caller_frame = self.frame_returning.f_back
            if caller_frame and not caller_frame.f_trace:
                caller_frame.f_trace = self.trace_dispatch
        self._set_stopinfo(None, None)

    def set_next(self, frame):
        """Stop on the next line in or below the given frame."""
        self._set_stopinfo(frame, None)

    def set_return(self, frame):
        """Stop when returning from the given frame."""
        self._set_stopinfo(frame.f_back, frame)

    def set_trace(self, frame=None):
        """Start debugging from frame.

        If frame is not specified, debugging starts from caller's frame.
        """
        if frame is None:
            frame = TracableFrame.CURRENT_FRAME.f_back
        self.reset()
        while frame:
            frame.f_trace = self.trace_dispatch
            self.botframe = frame
            frame = frame.f_back
        self.set_step()
        GlobalTracer.settrace(self.trace_dispatch)

    def set_continue(self):
        """Stop only at breakpoints or when finished.

        If there are no breakpoints, set the system trace function to None.
        """
        # Don't stop except at breakpoints or when finished
        self._set_stopinfo(self.botframe, None, -1)
        if not self.breaks:
            # no breakpoints; run without debugger overhead
            GlobalTracer.settrace(None)
            frame = TracableFrame.CURRENT_FRAME.f_back
            while frame and frame is not self.botframe:
                del frame.f_trace
                frame = frame.f_back

    def set_quit(self):
        """Set quitting attribute to True.

        Raises BaseDebuggerQuit exception in the next call to a dispatch_*() method.
        """
        self.stopframe = self.botframe
        self.returnframe = None
        self.quitting = True
        GlobalTracer.settrace(None)

    # Derived classes and clients can call the following methods
    # to manipulate breakpoints.  These methods return an
    # error message if something went wrong, None if all is well.
    # Set_break prints out the breakpoint line and file:lineno.
    # Call self.get_*break*() to see the breakpoints or better
    # for bp in Breakpoint.bpbynumber: if bp: bp.bpprint().

    def set_break(self, filename, lineno, temporary=False, cond=None,
                  funcname=None):
        """Set a new breakpoint for filename:lineno.

        If lineno doesn't exist for the filename, return an error message.
        The filename should be in canonical form.
        """
        filename = self.canonic(filename)
        import linecache # Import as late as possible
        line = linecache.getline(filename, lineno)
        if not line:
            return 'Line %s:%d does not exist' % (filename, lineno)
        list = self.breaks.setdefault(filename, [])
        if lineno not in list:
            list.append(lineno)
        Breakpoint(filename, lineno, temporary, cond, funcname)
        return None

    def _prune_breaks(self, filename, lineno):
        """Prune breakpoints for filename:lineno.

        A list of breakpoints is maintained in the BaseDebugger instance and in
        the Breakpoint class.  If a breakpoint in the BaseDebugger instance no
        longer exists in the Breakpoint class, then it's removed from the
        BaseDebugger instance.
        """
        if (filename, lineno) not in Breakpoint.bplist:
            self.breaks[filename].remove(lineno)
        if not self.breaks[filename]:
            del self.breaks[filename]

    def clear_break(self, filename, lineno):
        """Delete breakpoints for filename:lineno.

        If no breakpoints were set, return an error message.
        """
        filename = self.canonic(filename)
        if filename not in self.breaks:
            return 'There are no breakpoints in %s' % filename
        if lineno not in self.breaks[filename]:
            return 'There is no breakpoint at %s:%d' % (filename, lineno)
        # If there's only one bp in the list for that file,line
        # pair, then remove the breaks entry
        for bp in Breakpoint.bplist[filename, lineno][:]:
            bp.deleteMe()
        self._prune_breaks(filename, lineno)
        return None

    def clear_bpbynumber(self, arg):
        """Delete a breakpoint by its index in Breakpoint.bpbynumber.

        If arg is invalid, return an error message.
        """
        try:
            bp = self.get_bpbynumber(arg)
        except ValueError as err:
            return str(err)
        bp.deleteMe()
        self._prune_breaks(bp.file, bp.line)
        return None

    def clear_all_file_breaks(self, filename):
        """Delete all breakpoints in filename.

        If none were set, return an error message.
        """
        filename = self.canonic(filename)
        if filename not in self.breaks:
            return 'There are no breakpoints in %s' % filename
        for line in self.breaks[filename]:
            blist = Breakpoint.bplist[filename, line]
            for bp in blist:
                bp.deleteMe()
        del self.breaks[filename]
        return None

    def clear_all_breaks(self):
        """Delete all existing breakpoints.

        If none were set, return an error message.
        """
        if not self.breaks:
            return 'There are no breakpoints'
        for bp in Breakpoint.bpbynumber:
            if bp:
                bp.deleteMe()
        self.breaks = {}
        return None

    def get_bpbynumber(self, arg):
        """Return a breakpoint by its index in Breakpoint.bybpnumber.

        For invalid arg values or if the breakpoint doesn't exist,
        raise a ValueError.
        """
        if not arg:
            raise ValueError('Breakpoint number expected')
        try:
            number = int(arg)
        except ValueError:
            raise ValueError('Non-numeric breakpoint number %s' % arg) from None
        try:
            bp = Breakpoint.bpbynumber[number]
        except IndexError:
            raise ValueError('Breakpoint number %d out of range' % number) from None
        if bp is None:
            raise ValueError('Breakpoint %d already deleted' % number)
        return bp

    def get_break(self, filename, lineno):
        """Return True if there is a breakpoint for filename:lineno."""
        filename = self.canonic(filename)
        return filename in self.breaks and \
            lineno in self.breaks[filename]

    def get_breaks(self, filename, lineno):
        """Return all breakpoints for filename:lineno.

        If no breakpoints are set, return an empty list.
        """
        filename = self.canonic(filename)
        return filename in self.breaks and \
            lineno in self.breaks[filename] and \
            Breakpoint.bplist[filename, lineno] or []

    def get_file_breaks(self, filename):
        """Return all lines with breakpoints for filename.

        If no breakpoints are set, return an empty list.
        """
        filename = self.canonic(filename)
        if filename in self.breaks:
            return self.breaks[filename]
        else:
            return []

    def get_all_breaks(self):
        """Return all breakpoints that are set."""
        return self.breaks

    # Derived classes and clients can call the following method
    # to get a data structure representing a stack trace.

    def get_stack(self, f, t):
        """Return a list of (frame, lineno) in a stack trace and a size.

        List starts with original calling frame, if there is one.
        Size may be number of frames above or below f.
        """
        stack = []
        if t and t.tb_frame is f:
            t = t.tb_next
        while f is not None:
            stack.append((f, f.f_lineno))
            if f is self.botframe:
                break
            f = f.f_back
        stack.reverse()
        i = max(0, len(stack) - 1)
        while t is not None:
            stack.append((t.tb_frame, t.tb_lineno))
            t = t.tb_next
        if f is None:
            i = max(0, len(stack) - 1)
        return stack, i

    def format_stack_entry(self, frame_lineno, lprefix=': '):
        """Return a string with information about a stack entry.

        The stack entry frame_lineno is a (frame, lineno) tuple.  The
        return string contains the canonical filename, the function name
        or '<lambda>', the input arguments, the return value, and the
        line of code (if it exists).

        """
        frame, lineno = frame_lineno
        this_func = frame.address_module_function()
        s = '%s(%r)' % (this_func, lineno)
        line = frame.src_line()
        if line:
            s += lprefix + line.strip()
        return s


def set_trace():
    """Start debugging with a BaseDebugger instance from the caller's frame."""
    BaseDebugger().set_trace()


class Breakpoint:
    """Breakpoint class.

    Implements temporary breakpoints, ignore counts, disabling and
    (re)-enabling, and conditionals.

    Breakpoints are indexed by number through bpbynumber and by
    the (file, line) tuple using bplist.  The former points to a
    single instance of class Breakpoint.  The latter points to a
    list of such instances since there may be more than one
    breakpoint per line.

    When creating a breakpoint, its associated filename should be
    in canonical form.  If funcname is defined, a breakpoint hit will be
    counted when the first line of that function is executed.  A
    conditional breakpoint always counts a hit.
    """

    # XXX Keeping state in the class is a mistake -- this means
    # you cannot have more than one active BaseDebugger instance.

    next = 1        # Next bp to be assigned
    bplist = {}     # indexed by (file, lineno) tuple
    bpbynumber = [None] # Each entry is None or an instance of Bpt
                # index 0 is unused, except for marking an
                # _effective break .... see _effective()

    def __init__(self, file, line, temporary=False, cond=None, funcname=None):
        self.funcname = funcname
        # Needed if funcname is not None.
        self.func_first_executable_line = None
        self.file = file    # This better be in canonical form!
        self.line = line
        self.temporary = temporary
        self.cond = cond
        self.enabled = True
        self.ignore = 0
        self.hits = 0
        self.number = Breakpoint.next
        Breakpoint.next += 1
        # Build the two lists
        self.bpbynumber.append(self)
        if (file, line) in self.bplist:
            self.bplist[file, line].append(self)
        else:
            self.bplist[file, line] = [self]

    def deleteMe(self):
        """Delete the breakpoint from the list associated to a file:line.

        If it is the last breakpoint in that position, it also deletes
        the entry for the file:line.
        """

        index = (self.file, self.line)
        self.bpbynumber[self.number] = None   # No longer in list
        self.bplist[index].remove(self)
        if not self.bplist[index]:
            # No more bp for this f:l combo
            del self.bplist[index]

    def enable(self):
        """Mark the breakpoint as enabled."""
        self.enabled = True

    def disable(self):
        """Mark the breakpoint as disabled."""
        self.enabled = False

    def bpprint(self, out=None):
        """Print the output of bpformat().

        The optional out argument directs where the output is sent
        and defaults to standard output.
        """
        if out is None:
            out = sys.stdout
        print(self.bpformat(), file=out)

    def bpformat(self):
        """Return a string with information about the breakpoint.

        The information includes the breakpoint number, temporary
        status, file:line position, break condition, number of times to
        ignore, and number of times hit.

        """
        if self.temporary:
            disp = 'del  '
        else:
            disp = 'keep '
        if self.enabled:
            disp = disp + 'yes  '
        else:
            disp = disp + 'no   '
        ret = '%-4dbreakpoint   %s at %s:%d' % (self.number, disp,
                                                self.file, self.line)
        if self.cond:
            ret += '\n\tstop only if %s' % (self.cond,)
        if self.ignore:
            ret += '\n\tignore next %d hits' % (self.ignore,)
        if self.hits:
            if self.hits > 1:
                ss = 's'
            else:
                ss = ''
            ret += '\n\tbreakpoint already hit %d time%s' % (self.hits, ss)
        return ret

    def __str__(self):
        "Return a condensed description of the breakpoint."
        return 'breakpoint %s at %s:%s' % (self.number, self.file, self.line)

# -----------end of Breakpoint class----------


def _checkfuncname(b, frame):
    """Return True if break should happen here.

    Whether a break should happen depends on the way that b (the breakpoint)
    was set.  If it was set via line number, check if b.line is the same as
    the one in the frame.  If it was set via function name, check if this is
    the right function and if it is on the first executable line.
    """
    if not b.funcname:
        # Breakpoint was set via line number.
        if b.line != frame.f_lineno:
            # Breakpoint was set at a line with a def statement and the function
            # defined is called: don't break.
            return False
        return True

    # Breakpoint set via function name.
    if frame.function.name() != b.funcname:
        # It's impossible in move lang.
        # It's not a function call, but rather execution of def statement.
        return False

    # We are in the right frame.
    if not b.func_first_executable_line:
        # The function is entered for the 1st time.
        b.func_first_executable_line = frame.f_lineno

    if b.func_first_executable_line != frame.f_lineno:
        # But we are not at the first line number: don't break.
        return False
    return True


# Determines if there is an _effective (active) breakpoint at this
# line of code.  Returns breakpoint number or 0 if none
def _effective(file, line, frame):
    """Determine which breakpoint for this file:line is to be acted upon.

    Called only if we know there is a breakpoint at this location.  Return
    the breakpoint that was triggered and a boolean that indicates if it is
    ok to delete a temporary breakpoint.  Return (None, None) if there is no
    matching breakpoint.
    """
    possibles = Breakpoint.bplist[file, line]
    for b in possibles:
        if not b.enabled:
            continue
        if not _checkfuncname(b, frame):
            continue
        # Count every hit when bp is enabled
        b.hits += 1
        if not b.cond:
            # If unconditional, and ignoring go on to next, else break
            if b.ignore > 0:
                b.ignore -= 1
                continue
            else:
                # breakpoint and marker that it's ok to delete if temporary
                return (b, True)
        else:
            # Conditional bp.
            # Ignore count applies only to those bpt hits where the
            # condition evaluates to true.
            try:
                val = eval(b.cond, frame.f_globals, frame.f_locals) # TTODO: how to eval move?
                if val:
                    if b.ignore > 0:
                        b.ignore -= 1
                        # continue
                    else:
                        return (b, True)
                # else:
                #   continue
            except:
                # if eval fails, most conservative thing is to stop on
                # breakpoint regardless of ignore count.  Don't delete
                # temporary, as another hint to user.
                return (b, False)
    return (None, None)

