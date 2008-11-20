#!/usr/bin/python

import cgi, os, re, imp
from os.path import join
from time import time, localtime, strftime
from xml.sax.saxutils import escape

DEBUG = False

state = dict(
    blog_title = "My Weblog",
    blog_description = "One of the few constrictor blogs.",
    blog_language = "en",
    datadir = "/Library/WebServer/Documents/constrictor",
    url = "",
    depth = 0,
    num_entries = 40,
    file_extension = "txt",
    default_flavor = "html",
    show_future_entries = False,
    plugin_dir = "",
    plugin_state_dir = "",
    static_dir = "/Library/WebServer/Documents/blog",
    static_password = "",
    static_flavors = ["html", "rss"],
    static_entries = True
)

def load_plugins(dir):
    files = os.listdir(dir)
    files.sort()
    plugins = []
    for f in files:
        if f.endswith('.py'):
            name = f[:-3]
            plugin = imp.load_module(name, open(join(dir, f)), f, ('.py', 'r', imp.PY_SOURCE))
            plugin = plugin.start(state)
            if plugin is not None:
                plugins.append(plugin)
    return plugins

def get_path():
    path = os.environ.get('PATH_INFO')
    if path is None:
        return [];
    return [x for x in path.split('/') if x != ''];

def plugin_callback(name, mode, *args):
    destargs = [state] + [x for x in args]
    retval = None
    if mode == 2:
        retval = args[0]
    for p in state['plugins']:
        if hasattr(p, name):
            retval = apply(getattr(p, name), destargs)
            if mode == 1 and retval:
                return retval
            if mode == 2:
                destargs[1] = retval
    return retval

def default_template(state, path, chunk, flavor):
    basedir = state['datadir']
    for i in range(len(path), -1, -1):
        targetpath = join(basedir, *(path[:i] + [chunk + '.' + flavor]))
        if os.path.exists(targetpath):
            return open(targetpath).read()
    return state['templates'][flavor][chunk] or state['templates']['error'][chunk] or ''

def default_interpolate(state, data):
    return data % state

def default_sort(state, files):
    keys = files.keys()
    keys.sort(None, lambda x: files[x])
    keys.reverse()
    return keys

def default_entries(state):
    files, indexes, others = {}, {}, {}
    for dir, dirs, filelist in os.walk(state['datadir']):
        subdir = dir[len(state['datadir']) + 1:]
        for f in filelist:
            mtime = os.stat(join(dir, f)).st_mtime
            if (re.match(r'(.+)\.' + state['file_extension'], f) 
                and not f.startswith("index") 
                and not f.startswith('.')):

                if not state['show_future_entries'] and mtime > time():
                    continue
                files[join(dir, f)] = mtime
                ifile = join(state['static_dir'], subdir, 'index.' + state['static_flavors'][0])
                if state['-all'] or not os.path.exists(ifile) or os.stat(ifile).st_mtime < mtime:
                    indexes[subdir] = True
                    d = strftime("%Y/%m/%d", localtime(mtime))
                    indexes[d] = d
                    if state['static_entries']:
                        indexes[(subdir and subdir + '/' or '') + f] = True
            else:
                others[join(dir, f)] = mtime
    return files, indexes, others

def main():
    if DEBUG:
        print "Content-type: text/plain"
        print
    
    if state['plugin_dir']:
        state['plugins'] = load_plugins(state['plugin_dir'])
    else:
        state['plugins'] = []

    state['templates'] = {}

    if not state['url'] and os.environ.has_key('SCRIPT_NAME'):
        state['url'] = os.environ.get('SCRIPT_NAME')
    if state['url'].endswith('/'):
        state['url'] = state['url'][:-1]

    form = cgi.FieldStorage()

    state['static'] = (not os.environ.has_key("GATEWAY_INTERFACE")
                       and form.has_key('-password')
                       and state['static_password'] == form['-password'].value)
    
    state['-all'] = form.has_key('-all')

    path = get_path()
    
    date = [x for x in path if re.match("[0-9].*", x)]
    if len(date) > 0:
        state['path_year'] = int(date[0])
    else:
        state['path_year'] = ''
    if len(date) > 1:
        state['path_month'] = int(date[1])
    else:
        state['path_month'] = ''
    if len(date) > 2:
        state['path_day'] = int(date[2])
    else:
        state['path_day'] = ''

    state['flavor'] = state['default_flavor']

    path = [x for x in path if not re.match("[0-9].*", x)]
    if len(path) > 0:
        m = re.match(r'(.+)\.(.+)$', path[-1])
        if m:
            state['flavor'] = m.group(2)
            if m.group(1) == 'index':
                path = path[:-1]
            else:
                path[-1] = m.group(1) + '.' + state['file_extension']

    if form.has_key('flavor'):
        state['flavor'] = form['flavor'].value

    state['category'] = path

    global template
    template = plugin_callback('template', 1) or default_template

    global entries
    entries = plugin_callback('entries', 1) or default_entries

    state['files'], state['indexes'], state['others'] = entries(state)

    plugin_callback('filter', 0)

    if state['static']:
        print "Generating static index pages..."
        finished = []
        for path in state['indexes']:
            p = ''
            for segment in path.split('/'):
                if p:
                    p += '/' + segment
                else:
                    p = segment
                if p in finished:
                    continue
                else:
                    finished.append(p)
                if not p.endswith('.' + state['file_extension']) and not os.path.exists(join(state['static_dir'], p)):
                    os.mkdir(join(state['static_dir'], p), 0755)
                for flavor in state['static_flavors']:
                    content_type = template(state, p.split('/'), 'content_type', flavor).split('\n')[0]
                    file = p.endswith('.' + state['file_extension']) and p[:-4] or join(p, 'index')
                    if state['indexes'][path] is True:
                        data = generate(p.split('/'), ['','',''], flavor, content_type)
                    else:
                        date = p.split('/')
                        for i in range(3):
                            if len(date) > i:
                                date[i] = int(date[i])
                            else:
                                date.append('')
                        data = generate([], date, flavor, content_type)
                    if data:
                        print file + '.' + flavor
                        output = open(join(state['static_dir'], file + '.' + flavor), 'w')
                        if not output:
                            raise "Could not open " + join(state['static_dir'], file + '.' + flavor)
                        output.write(data)
                        output.close()
    else:
        content_type = template(state, state['category'], 'content_type', state['flavor']).split('\n')[0]
        state['header'] = "Content-Type: " + content_type
        content = generate(state['category'],
                           (state['path_year'], state['path_month'], state['path_day']),
                           state['flavor'],
                           content_type)
        if content:
            print state['header']
            print
            print content

def generate(currentdir, date, flavor, content_type):
    if plugin_callback('skip', 1, currentdir, date):
        return ''

    interpolate = plugin_callback('interpolate', 1) or default_interpolate

    head = template(state, currentdir, 'head', flavor)
    head = plugin_callback('head', 2, head, currentdir)
    head = interpolate(state, head)

    output = []
    output.append(head)

    files_to_parse = state['files']
    
    if currentdir:
        path = join(state['datadir'], *currentdir)
        if re.match(r'(.+)\.' + state['file_extension'], currentdir[-1]) and state['files'].has_key(path):
            files_to_parse = { path : state['files'][path] }

    entries_left = state['num_entries']

    sort = plugin_callback('sort', 1) or default_sort

    curdate = None

    for f in sort(state, files_to_parse):
        if entries_left <= 0:
            break
        m = re.match(state['datadir'] + r'/(?:(.*)/)?(.+)\.' + state['file_extension'], f)
        state['path'], state['file'] = m.group(1) or '', m.group(2)

        # Skip entries not on the proper path
        if not state['path'].startswith(join('', *currentdir)) and not f == join(state['datadir'], *currentdir):
            continue
        state['path'] = state['path'] and ('/' + state['path'])

        mdate = localtime(state['files'][f])
        if date[0] and mdate[0] != date[0]:
            continue
        if date[1] and mdate[1] != date[1]:
            continue
        if date[2] and mdate[2] != date[2]:
            continue
        state['year'], state['month'], state['day'], state['hour'], state['min'], state['sec'], state['wday'], state['yday'], state['isdst'] = mdate
        state['month_name'], state['wday_name'] = strftime("%b", mdate), strftime("%a", mdate)
        datetext = template(state, currentdir, 'date', flavor)
        
        datetext = plugin_callback('date', 2, datetext, currentdir, mdate)

        datetext = interpolate(state, datetext)

        if curdate != datetext:
            curdate = datetext
            output.append(datetext)

        text = open(f)
        state['title'] = text.readline()[:-1]
        state['body'] = text.read()
        text.close()
        story = template(state, currentdir, 'story', flavor)
        
        story = plugin_callback('story', 2, story, currentdir)

        if content_type.find('xml') > -1:
            state['title'] = escape(state['title'])
            state['body'] = escape(state['body'])

        story = interpolate(state, story)

        output.append(story)

        entries_left -= 1

    foot = template(state, currentdir, 'foot', flavor)
    
    foot = plugin_callback('foot', 2, foot)

    foot = interpolate(state, foot)
    output.append(foot)

    output = plugin_callback('last', 2, output)

    return ''.join(output)
        
if __name__ == '__main__':
    main()

