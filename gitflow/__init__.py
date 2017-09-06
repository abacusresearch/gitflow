import gettext

gettext.bindtextdomain('gitflow', 'res/translations')
gettext.textdomain('gitflow')
_ = gettext.gettext
# _ = lambda x: x
