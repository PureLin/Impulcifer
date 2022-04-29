import os, shutil
import tkinter
import re
from tkinter import *
from tkinter.filedialog import askdirectory, askopenfilename, asksaveasfilename
from tkinter.messagebox import showinfo
import recorder, impulcifer
import sounddevice


# tooltip for widgets
class ToolTip(object):
    def __init__(self, widget, text='widget info'):
        self.waittime = 500  # miliseconds
        self.wraplength = 180  # pixels
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)
        self.id = None
        self.tw = None

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.waittime, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        x = y = 0
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        # creates a toplevel window
        self.tw = Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = Label(self.tw, text=self.text, justify='left',
                      background="#ffffff", relief='solid', borderwidth=1,
                      wraplength=self.wraplength)
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()


# decimal entry validator
def validate_double(inp):
    if not inp or inp == '-':
        return True
    try:
        float(inp)
    except:
        return False
    return True


# integer entry validator
def validate_int(inp):
    if not inp:
        return True
    try:
        int(inp)
    except:
        return False
    if len(inp) > 5:  # limit chars to 5
        return False
    if '-' in inp:
        return False
    return True


# open dir dialog
def opendir(var):
    path = askdirectory(initialdir=os.path.dirname(var.get()))
    if not path:
        return
    path = os.path.abspath(path)  # make all separators the correct one
    path = path.replace(os.getcwd() + os.path.sep, '')  # prefer relative paths when possible
    var.set(path)


# open file dialog
def openfile(var, filetypes):
    path = askopenfilename(initialdir=os.path.dirname(var.get()), initialfile=os.path.basename(var.get()),
                           filetypes=filetypes)
    if not path:
        return
    path = os.path.abspath(path)
    path = path.replace(os.getcwd() + os.path.sep, '')
    var.set(path)


# save file dialog
def savefile(var):
    path = asksaveasfilename(initialdir=os.path.dirname(var.get()), initialfile=os.path.basename(var.get()),
                             defaultextension=".wav", filetypes=(('WAV file', '*.wav'), ('All files', '*.*')))
    if not path:
        return
    path = os.path.abspath(path)
    path = path.replace(os.getcwd() + os.path.sep, '')
    var.set(path)


# pack widget into canvas
def pack(widget, samerow=False):
    if not samerow:
        pos[1] += widget.winfo_reqheight() + 5
        pos[0] = 10
    widget.place(x=pos[0], y=pos[1], anchor=W)
    widgetpos = (pos[0], pos[1])
    pos[0] += widget.winfo_reqwidth()
    global maxwidth
    maxwidth = max(maxwidth, pos[0])
    global maxheight
    maxheight = pos[1] + 20
    root.update()
    return widgetpos


# RECORDER WINDOW
root = Tk()

root.title('12 Channel BRIR QuickCreate')
root.resizable(False, False)
canvas1 = Canvas(root)

pos = [0, 0]
maxwidth = 0
maxheight = 0


# refresh record window
def refresh1(init=False):
    host_apis = {}
    i = 0
    for host in sounddevice.query_hostapis():
        host_apis[i] = host['name']
        i += 1

    host_api_optionmenu['menu'].delete(0, 'end')
    for host in host_apis.values():
        host_api_optionmenu['menu'].add_command(label=host, command=tkinter._setit(host_api, host))

    if not host_apis:
        host_api.set('')
    elif init and 'Windows DirectSound' in host_apis.values():
        host_api.set('Windows DirectSound')
    elif host_api.get() not in host_apis.values():
        host_api.set(host_apis[0])

    output_devices = []
    input_devices = []
    for device in sounddevice.query_devices():
        if host_apis[device['hostapi']] == host_api.get():
            if device['max_output_channels'] > 0:
                output_devices.append(device['name'])
            elif device['max_input_channels'] > 0:
                input_devices.append(device['name'])
    output_device_optionmenu['menu'].delete(0, 'end')
    input_device_optionmenu['menu'].delete(0, 'end')
    for device in output_devices:
        output_device_optionmenu['menu'].add_command(label=device, command=tkinter._setit(output_device, device))
    for device in input_devices:
        input_device_optionmenu['menu'].add_command(label=device, command=tkinter._setit(input_device, device))
    if not output_devices:
        output_device.set('')
    elif output_device.get() not in output_devices:
        output_device.set(output_devices[0])
    if not input_devices:
        input_device.set('')
    elif input_device.get() not in input_devices:
        input_device.set(input_devices[0])


# playback device
output_device = StringVar()
output_device.trace('w', lambda *args: refresh1())
pack(Label(canvas1, text='Playback device'))
output_device_optionmenu = OptionMenu(canvas1, variable=output_device, value=None, command=refresh1)
pack(output_device_optionmenu, samerow=True)

# record device
input_device = StringVar()
input_device.trace('w', lambda *args: refresh1())
pack(Label(canvas1, text='Recording device'))
input_device_optionmenu = OptionMenu(canvas1, variable=input_device, value=None, command=refresh1)
pack(input_device_optionmenu, samerow=True)

# host API
pack(Label(canvas1, text='Host API'))
host_api = StringVar()
host_api.trace('w', lambda *args: refresh1())
host_api_optionmenu = OptionMenu(canvas1, host_api, value=None, command=refresh1)
pack(host_api_optionmenu, samerow=True)

# sound file to play
pack(Label(canvas1, text='File to play'))
play = StringVar(value=os.path.join('data', 'sweep-seg-FL-stereo-6.15s-48000Hz-32bit-2.93Hz-24000Hz.wav'))
play_entry = Entry(canvas1, textvariable=play, width=70)
pack(play_entry)
pack(Button(canvas1, text='...', command=lambda: openfile(play, (('Audio files', '*.wav'), ('All files', '*.*')))),
     samerow=True)

pack(Label(canvas1, text='Headphone File to play'))
hp_play = StringVar(value=os.path.join('data', 'sweep-seg-FL,FR-stereo-6.15s-48000Hz-32bit-2.93Hz-24000Hz.wav'))
hp_play_entry = Entry(canvas1, textvariable=hp_play, width=70)
pack(hp_play_entry)
pack(Button(canvas1, text='...', command=lambda: openfile(hp_play, (('Audio files', '*.wav'), ('All files', '*.*')))),
     samerow=True)

# output file
pack(Label(canvas1, text='Record directory'))
record = StringVar(value=os.path.join('temp'))
record_entry = Entry(canvas1, textvariable=record, width=70)
pack(record_entry)
pack(Button(canvas1, text='...', command=lambda: opendir(record)), samerow=True)


# record button
def recordaction():
    main_button.config(state='disabled')
    recorder.play_and_record(play=play_entry.get(),
                             record=record_entry.get() + "/" + str(layer.get()) + "/" + str(position.get()) + ".wav",
                             input_device=input_device.get(),
                             output_device=output_device.get(), host_api=host_api.get(),
                             channels=2, append=False)
    posVar.set((posVar.get() + 1) % 12)
    if posVar.get() == 0:
        layVar.set((layVar.get() + 1) % 5)
    main_button.config(state='normal')


def record_headphones():
    headphones.config(state='disabled')
    recorder.play_and_record(play=hp_play_entry.get(),
                             record=record_entry.get() + "/headphones.wav",
                             input_device=input_device.get(),
                             output_device=output_device.get(), host_api=host_api.get(),
                             channels=2, append=False)
    headphones.config(state='normal')


# record button
def start_impulcifer():
    temp_dir = record_entry.get()
    if not os.path.exists(temp_dir + "/headphones.wav"):
        errorLabel.config(text="headphones.wav not exist")
        return
    if not os.path.exists(temp_dir + "/test.wav"):
        errorLabel.config(text="test.wav not exist")
        return
    for i in range(0, 4):
        if os.path.exists(temp_dir + "/" + str(i)):
            shutil.copyfile(temp_dir + "/headphones.wav", temp_dir + "/" + str(i) + "/headphones.wav")
            shutil.copyfile(temp_dir + "/test.wav", temp_dir + "/" + str(i) + "/test.wav")
            impulcifer.main(temp_dir + "/" + str(i))


pack(Label(canvas1, text='Position'))
posVar = IntVar()
posVar.set(0)
position = Spinbox(canvas1, textvariable=posVar, from_=0, to=11)
pack(position, True)
pack(Label(canvas1, text='Layer'), True)
layVar = IntVar()
layVar.set(2)
layer = Spinbox(canvas1, textvariable=layVar, from_=0, to=4)
pack(layer, True)

main_button = Button(canvas1, text='Record ', command=recordaction)
pack(main_button)
headphones = Button(canvas1, text='Record headphones', command=record_headphones)
pack(headphones, True)

impulcifer_button = Button(canvas1, text='impulcifer', command=start_impulcifer)
pack(impulcifer_button)
errorLabel = Label(canvas1, text="")
pack(errorLabel, True)

refresh1(init=True)
root.geometry(str(maxwidth) + 'x' + str(maxheight) + '+0+0')
canvas1.config(width=maxwidth, height=maxheight)
canvas1.pack()

root.mainloop()
