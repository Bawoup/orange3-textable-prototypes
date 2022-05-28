__version__ = u"0.0.1"
__author__ = "Zakari Rabet"
__maintainer__ = "Zakari Rabet"
__email__ = "rabet.zakari@gmail.ch"

# Standard imports...
import re, json, csv, os, platform, codecs, inspect
from xml.dom import InuseAttributeErr


from Orange.widgets import widget, gui, settings
from Orange.widgets.widget import OWWidget, Input, Output
from Orange.widgets.utils.widgetpreview import WidgetPreview
from enum import Enum
from pathlib import Path
from LTTL.Segmentation import Segmentation
from LTTL.Segment import Segment
from LTTL.Segmenter import bypass
from PyQt5.QtWidgets import QMessageBox
from PyQt4.QtGui import QTabWidget, QWidget, QHBoxLayout
from _textable.widgets.TextableUtils import (
    OWTextableBaseWidget, VersionedSettingsHandler,
    JSONMessage, InfoBox, SendButton, AdvancedSettings,
    ProgressBar, pluralize
)

__version__ = "0.0.1"


class Parathon(OWTextableBaseWidget):
    """An Orange widget that lets extract paratextual elements from a text"""
        
    #----------------------------------------------------------------------
    # Widget's metadata...
    name = "Parathon Matthieu"
    description = "Extract paratextual elements"
    icon = "icons/parathon.svg"
    priority = 12
        
    #----------------------------------------------------------------------    
    # Input and output channels...
    inputs = [
        ('Segmentation', Segmentation, 'inputData',)]
    outputs = [('Segmented data', Segmentation)]

    #----------------------------------------------------------------------
    # Settings...
    
    settingsHandler = VersionedSettingsHandler(
        version=__version__.rsplit(".", 1)[0]
    )
    
    want_main_area = False
    
    autoSend = settings.Setting(False)
    displayAdvancedSettings = settings.Setting(False)
    
    
    selectedDictionaries = settings.Setting([])
    dictLabels = settings.Setting([])
    defaultDict = settings.Setting({})
    
    selectedSubDictionaries = settings.Setting([])
    subDictLabels = settings.Setting([])
    subDictUniqueLabels = settings.Setting(set())
    f2fDictLabels = settings.Setting([])
    cmcDictLabels = settings.Setting([])
    subDict = settings.Setting({})
    

    def __init__(self):
        super().__init__()
        
        # Other attributes...
        
        
        #-------------------------------------------------------------------
        # GUI...

        self.inputsegmentation = None
        self.infoBox = InfoBox(widget=self.controlArea)
        self.sendButton = SendButton(
            widget=self.controlArea,
            master=self,
            callback=self.sendData,
            infoBoxAttribute="infoBox",
            sendIfPreCallback=None
        )
        
        # Advanced settings...
        self.advancedSettings = AdvancedSettings(
            widget=self.controlArea,
            master=self,
            callback=self.showAdvancedSettings,
        )
        
        self.advancedSettings.draw()
        

        # Global box
        self.globalBox = gui.widgetBox(
            widget=self.controlArea,
            box=False,
            orientation='horizontal',
            )
    
        # Dictionaries box
        self.dictBox = gui.widgetBox(
            widget=self.globalBox,
            box="Dictionaries",
            orientation="vertical",
            )
        self.dictListBox = gui.listBox(
            widget=self.dictBox,
            master=self,
            value="selectedDictionaries",
            labels="dictLabels",
            callback=self.getSubDictList,
            tooltip="The list of dictionaries containing the regex to apply",
            )
        
        self.dictBox.setMinimumHeight(40)
        self.dictBox.setMinimumWidth(50)
        self.dictListBox.setSelectionMode(2)
        gui.separator(widget=self.dictBox, height=3)
        
        # Create a button box for the two next buttons
        selectionBox = gui.widgetBox(
            widget=self.dictBox,
            box=False,
            orientation='horizontal',
        )
        
        # SelectAll Button
        self.selectAll = gui.button(
            widget=selectionBox,
            master=self,
            label="Select All",
            callback=self.selectAll,
            tooltip="Select every dictionary of the list.",
        )

        # DeselectAll Button
        self.deselectAll = gui.button(
            widget=selectionBox,
            master=self,
            label="Deselect All",
            callback=self.deselectAll,
            tooltip="Deselect every dictionary from the list.",
        )
        
        # Create a button box for the refresh button
        refreshBox = gui.widgetBox(
            widget=self.dictBox,
            box=False,
            orientation='horizontal',
        )
        
        # Reload button
        self.refreshDict = gui.button(
            widget=refreshBox,
            master=self,
            label="Reload",
            callback=self.getDictList,
            tooltip="Refresh dictionary List",
            )

        #-------------------------------------------------------------------
        # Advanced settings box
        self.advancedBox = gui.widgetBox(
            widget=self.globalBox,
            box="Selection Mode",
            orientation="vertical",
        )
        
        # Radio Button
        self.cmcButtons = gui.radioButtonsInBox(
        widget=self.advancedBox,
        master=self,
        box=False,
        btnLabels=['CMC', 'F2F'],
        callback=self.processRadioButton,
        value='subDict',
        )
        
        self.cmcButtons.setMinimumHeight(80)
        self.cmcButtons.setMinimumWidth(40)
        
        self.subDictBox = gui.widgetBox(
            widget=self.advancedBox,
            box=False,
            orientation="vertical",
            )
        
        self.subDictListBox = gui.listBox(
            widget=self.subDictBox,
            master=self,
            value="selectedSubDictionaries",
            labels="subDictLabels",
            callback=None,
            tooltip="The list of sub dictionaries containing the regex to apply",
            )
        
        self.subDictListBox.setSelectionMode(2)
        
        # GUI separator...
        gui.separator(widget=self.globalBox)
        
        self.advancedSettings.advancedWidgets.append(self.advancedBox)
        self.advancedSettings.advancedWidgetsAppendSeparator()
        
        self.getDictList()
        
        self.sendButton.draw()
        self.infoBox.draw()
        
        self.advancedSettings.setVisible(self.displayAdvancedSettings)
    
    def print(self):
        print(self.selectedSubDictionaries)

    def showAdvancedSettings(self):
        self.advancedSettings.setVisible(self.displayAdvancedSettings)
    
    def inputData(self, Segmentation, language=None, mode=None):
        # Process incoming segmentation
        self.inputsegmentation = Segmentation
        self.language = language
        self.mode = mode
        self.infoBox.inputChanged()
        self.sendButton.sendIf()
        

    # Function for the detection of paralinguistic cues
    def parathonFunction(self, file, dicts, ftfList, cmcList):
   
        # Dictionnaire où sera stocké les regex à utiliser selon les choix de CMC ou FTF
        cue_dictionary = {}

        if not ftfList and not cmcList:
            # Looper chaque dictionnaire choisi
            for dict in dicts:
                #Ouvrir le dictionnaire qui est sous format json
                f = open('dictionaries/'+dict+'.json', encoding='utf-8')
                data = json.load(f)
                # Aller chercher les keys du dictionnaire
                keys = list(data)
                print(len(keys))
                # Combiner ces dictionnaires dans cue_dictionary
                for key in keys:
                    cue_dictionary[key] = data[key]
        else:
            # Looper chaque dictionnaire choisi
            for dict in dicts:
                #Ouvrir le dictionnaire qui est sous format json
                f = open('dictionaries/'+dict+'.json', encoding='utf-8')
                data = json.load(f)
                # Aller chercher les keys du dictionnaire
                keys = list(data)
                # On va chercher la liste qui n'est pas vide (FTF ou CMC) et on déclare la variable selection et la variable index
                if ftfList:
                    print("FTF selected")
                    selection = ftfList
                    index = 0
                if cmcList:
                    print("CMC selected")
                    selection = cmcList
                    index = 1
            # Une fois ces deux variables déclarées on utilise leur valeur
            # Pour chaque CMC ou FTF choisi on va aller prendre les regex associées dans chaque dictionnaire puis l'ajouter à un nouveau dictionnaire (--> cue_dictionary)
                for element in selection:
                    for key in keys : 
                        regex1 = re.escape(element)+r"\W"
                        regex2 = re.escape(element)+r"\Z"
                        if re.search(regex1, str(data[key][index])) or re.search(regex2, str(data[key][index])):
                            cue_dictionary[key] = data[key]
                
        #print(len(cue_dictionary))

        #file = open(file, "r", encoding="utf8")
        #txt = file.read()
        txt = file

        # Here we split the text into tokens. Emojis count as tokens. Some punctuation
        # is included as a word character so we may take into account,
        # for example, *corrections and _whatsapp formatting_.

        split = re.findall(r"[\w'*_~]+|[.,!?;:)\*]+|\s+|[\U00010000-\U0010ffff]", txt, flags=re.UNICODE)
        position = 0
        output = list()
        for token in split:
            start = position
            position = position + len(token)
            end = position
            matches_for_token = list()
            for key in cue_dictionary:
                # Some of the regexes require flags.
                # This part allows us to use those flags.
                try:
                    if cue_dictionary[key][3]:
                        if re.search(key, token, flags=eval(cue_dictionary[key][3])):
                            matches_for_token.append([token, cue_dictionary[key], start, end])
                except IndexError:
                    if re.search(key, token):
                        matches_for_token.append([token, cue_dictionary[key], start, end])
            # Append properties to lists for later
            if len(matches_for_token) > 1:
                ftf_properties = list()
                cmc_properties_main = list()
                cmc_properties_sub = list()
                for match in matches_for_token:
                    ftf_properties.append(match[1][0])
                    cmc_properties_main.append(match[1][1])
                    cmc_properties_sub.append(match[1][2])
            elif len(matches_for_token) == 1:
                ftf_properties = matches_for_token[0][1][0]
                cmc_properties_main = matches_for_token[0][1][1]
                cmc_properties_sub = matches_for_token[0][1][2]
            elif (token, " ", " ", start, end) not in output:
                ftf_properties = " "
                cmc_properties_main = " "
                cmc_properties_sub = " "
            output.append((token, ftf_properties, cmc_properties_main, cmc_properties_sub, start, end))
        
        # Transform output to xml format
        output_str_xml = '<?xml version="1.0" encoding="UTF-8"?>\n\t<input>'
        xml_output=list()
        for token in output:
            if token[1]!=" ":
                token_info_xml='<cue f2f="'+str(token[1])+'" cmc_main="'+str(token[2])+'" cmc_sub="'+str(token[3])+'">'+str(token[0])+'</cue>'
                xml_output.append(token_info_xml)
            else:
                xml_output.append(token[0])
        for token in xml_output:
            output_str_xml = output_str_xml + token
        output_str_xml = output_str_xml + "\n</input>"


        print(output_str_xml)
        return output_str_xml
    
    def sendData(self):
        
        # True si advanced setting coché et False sinon
        AS_SelectionStatus = self.displayAdvancedSettings
        print("Advanced Settings is selected : " + str(AS_SelectionStatus))

        # Dictionnaires sélectionnés
        selectedDictsLabels = [self.dictLabels[item] for item in self.selectedDictionaries]
        print(selectedDictsLabels)

        # Sous-Dictionnaires (les CMTs ou FTFs) sélectionnés
        selectedSubDictsLabels = [list(self.subDictUniqueLabels)[item] for item in self.selectedSubDictionaries]
        print(selectedSubDictsLabels)


        # Determine ici le mode de sélection coché
        if isinstance(self.subDict, int) and AS_SelectionStatus==True:
            selectedMode = ['CMC', 'F2F'][self.subDict]
            print(selectedMode + " is selected")
            # Assigner les valeurs de CMTs ou FTFs à des listes
            if selectedMode == "CMC":
                cmcList = selectedSubDictsLabels
                ftfList = []
            
            if selectedMode == "F2F":
                cmcList = []
                ftfList = selectedSubDictsLabels
            print(cmcList, ftfList)
        else:
            cmcList = []
            ftfList = []
            print(cmcList, ftfList)
            print("Neither CMC or F2F are selected")

            
        # Preprocess and send data
        if not self.inputsegmentation:
            self.infoBox.setText(u'Widget needs input.', 'warning')
            self.send('Segmented data', None, self)
            return
        # if advancedSettings: # renommer selon le code
            # return
        else :
            
        
            self.infoBox.setText(u"Processing, please wait...", "warning")
            self.controlArea.setDisabled(True)
            progressBar = ProgressBar(
                self,
                iterations=len(self.inputsegmentation)
            )
            bypassed_data = bypass(self.inputsegmentation, label=self.captionTitle)


            textInput = self.inputsegmentation.get_data(0)
            print(textInput)
            print(selectedDictsLabels)
            print(ftfList)
            print(cmcList)

            self.parathonFunction(textInput, selectedDictsLabels, ftfList, cmcList)
            


            #print(self.inputsegmentation)
            #print(bypassed_data)
            #print(self.inputsegmentation.get_data(0))
            #inputtext = self.inputsegmentation.get_data(0) + " plus another simple example"

            #testbypassed_data = Input(inputtext)
            #print(testbypassed_data)
            #bypassed_data = "hello"
            #print(bypassed_data)

            progress_callback=progressBar.advance
            progressBar.finish()
            self.controlArea.setDisabled(False)
            message = u'%i segment@p sent to output.' % len(bypassed_data)
            message = pluralize(message, len(bypassed_data))
            self.infoBox.setText(message)
            #self.send('Segmented data', bypassed_data, self)
            self.send('Segmented data', bypassed_data, self)
            self.sendButton.resetSettingsChangedFlag()
            
        
    def getDictList(self):        
        # Setting the path of the file and retrieving file dictionary names
        actualFolderPath = os.path.dirname(
            os.path.abspath(inspect.getfile(inspect.currentframe()))
        )
        folderPath = os.path.join(actualFolderPath, "dictionaries")
        
        self.defaultDict = {} # nom du fichier et contenu du fichier
        for file in os.listdir(folderPath):
            if file.endswith(".json"):
                # Gets json file name and substracts .json extension
                fileName = os.path.splitext(os.path.basename(file))[0]
                self.defaultDict.update({fileName: ''})
                
                # Open json files and stores their content
                try:
                    filePath = os.path.join(folderPath, file)
                    fileOpened = codecs.open(filePath, encoding='utf-8')
                    fileLoaded = json.load(fileOpened)
                    self.defaultDict[fileName] = fileLoaded
                except IOError:
                    QMessageBox.warning(
                        None,
                        'Parathon',
                        "Couldn't open file.",
                        QMessageBox.Ok
                    )
        
        # Sorts defaultDict and display the right titles in the listBox            
        self.dictLabels = sorted(self.defaultDict.keys())
    
    def getSubDictList(self):
        self.cmcDictLabels = []
        self.f2fDictLabels = []
        for key in self.selectedDictionaries:
            subDictLabelsList = self.defaultDict[self.dictLabels[key]].values()
            for subDictLabel in subDictLabelsList:
                self.f2fDictLabels.append(subDictLabel[0])
                self.cmcDictLabels.append(subDictLabel[1])
        self.processRadioButton()
    
    def processRadioButton(self):  
        self.subDictLabels = []
        tempList = []
        self.subDictUniqueLabels = set()

        if self.subDict == 0 or not self.subDict:
            for elem in self.cmcDictLabels:
                if ',' in elem:
                    tempElems = elem.split(', ')
                    tempList.append(tempElems)
                else:
                    tempList.append(elem)
            self.subDictUniqueLabels.update(tempList)
        elif self.subDict == 1:
            for elem in self.f2fDictLabels:
                if ',' in elem:
                    tempElems = elem.split(', ')
                    tempList.extend(tempElems)
                else:
                    tempList.append(elem)
            self.subDictUniqueLabels.update(tempList)
        else:
            print(self.subDict)
            QMessageBox.warning(
                        None,
                        'Parathon',
                        "Unvalid interaction.",
                        QMessageBox.Ok
                    )
        self.subDictLabels = list(self.subDictUniqueLabels)
        self.selectedSubDictionaries = list(range(len(self.subDictLabels)))
    
    def selectAll(self):
        self.selectedDictionaries = list(range(len(self.dictLabels)))
        self.getSubDictList()
  
    def deselectAll(self):
        self.selectedDictionaries = []
        self.getSubDictList()
    
    
    def setCaption(self, title):
        if 'captionTitle' in dir(self):
            changed = title != self.captionTitle
            super().setCaption(title)
            if changed:
                self.sendButton.settingsChanged()
        else:
            super().setCaption(title)
        

        
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from LTTL.Input import Input
    
    myApplication = QApplication(sys.argv)
    myWidget = Parathon()
    myWidget.inputData(Input('03/02/2021, 19:30 - sorcha: *LMAO'))
    myWidget.show()
    myApplication.exec_()
    myWidget.saveSettings()
        
