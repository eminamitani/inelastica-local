print "SVN $Id$"

import numpy as N
import numpy.linalg as LA
import string, struct, os.path, sys
import MakeGeom as MG
import gzip
import Scientific.IO.NetCDF as nc


def VIO_open(filename,mode='r'):
    "A VaspIO redefinition of the function open() to handle gzip format"
    try:
        if filename[-3:]=='.gz':
            # filename is explicitly a gzip file
            file = gzip.open(filename,mode)
        else:
            # filename is given as a non-zip file
            file = open(filename,mode)
    except:
        # if filename is not existing upon read, then try append the '.gz' ending
        file = gzip.open(filename+'.gz',mode)
    return file

#--------------------------------------------------------------------------------
# Interface with VASP

def ReadCONTCAR(filename):
    "Read CONTCAR file"
    print 'VaspIO.ReadCONTCAR: Reading', filename
    file = VIO_open(filename,'r')
    label = file.readline()
    scalefactor = float(file.readline())
    vectors = N.zeros((3,3),N.float)
    for ii in range(3):
        tmp = file.readline().split()
        vectors[ii] = N.array(tmp,N.float)
    speciesnumbers = N.array(file.readline().split(),N.int)
    natoms = N.sum(speciesnumbers)
    # Read 'Selective Dynamics' and 'Direct' lines
    file.readline()
    file.readline()
    # Read coordinates and degrees of freedom
    xyz = N.zeros((natoms,6),N.float)
    for ii in range(natoms):
        line = file.readline()
        line = line.replace('F','0')
        line = line.replace('T','1')
        line = line.split()
        xyz[ii] = N.array(line,N.float)
    # Ignore rest of the file
    file.close()
    # Convert to cartesian coordinates
    for ii in range(natoms):
        xyz[ii][:3] = xyz[ii,0]*vectors[0]+xyz[ii,1]*vectors[1]+xyz[ii,2]*vectors[2]
    return label,scalefactor,vectors,speciesnumbers,xyz

def WritePOSCAR(filename,vectors,speciesnumbers,xyz,label='LABEL',scalefactor=1.0,constrained=[]):
    "Write POSCAR file"
    print 'VaspIO.WritePOSCAR: Writing',filename
    file = open(filename,'w')
    if label[:-2]!='\n':
        file.write(label+'\n')
    else:
        file.write(label)
    file.write('  %.12f \n'%scalefactor)
    for ii in range(3):
        for jj in range(3):
            file.write(string.rjust('%.9f'%vectors[ii][jj],16)+' ')
        file.write('\n')
    for ii in range(len(speciesnumbers)):
        file.write('  %i'%speciesnumbers[ii])
    file.write('\n')
    file.write('Selective dynamics\nCartesian\n')
    for ii in range(len(xyz)):
        line  = string.rjust('%.9f'%xyz[ii][0],16)+' '
        line += string.rjust('%.9f'%xyz[ii][1],16)+' '
        line += string.rjust('%.9f'%xyz[ii][2],16)+' '
        if len(constrained)>0:
            for jj in range(3):
                if constrained[ii,jj] > 0:
                    line += ' T'
                else:
                    line += ' F'
            line += '\n'
        else:
            line += ' F F F\n'
        file.write(line)

def GetEnergies(OUTCAR):
    file = VIO_open(OUTCAR,'r')
    print 'VaspIO.GetEnergies: Reading', OUTCAR
    #
    freeE, Etot, EtotSigma0 = 1e100, 1e100, 1e100
    for line in file:
        if 'TOTEN' in line:
            l = line.split()
            freeE = float(l[4])      # Pick last appearance
        if 'energy  without entropy=' in line:
            l = line.split()
            Etot = float(l[3])       # Pick last appearance
            EtotSigma0 = float(l[6]) # Pick last appearance
    file.close()
    return freeE, Etot, EtotSigma0

def GetSpecies(OUTCAR):
    file = VIO_open(OUTCAR,'r')
    print 'VaspIO.GetSpecies: Reading', OUTCAR
    atoms = []
    for line in file:
        if 'VRHFIN' in line:
            l = line.split()
            atoms += [l[1][1:-1]]
    return atoms

def GetVibModesNoScaling(OUTCAR):
    file = VIO_open(OUTCAR,'r')
    print 'VaspIO.GetVibrations: Reading', OUTCAR
    freq = []
    modes = []
    v = []    
    datablock = False
    for line in file:
        if 'Eigenvectors and eigenvalues of the dynamical matrix' in line:
            datablock = True # beginning of data block
        if 'Eigenvectors after division by SQRT(mass)' in line \
               or 'Finite differences POTIM=' in line:
            datablock = False # end of data block
        if datablock:
            l = line.split()
            if 'meV' in line:
                # grep frequency
                print line,
                freq.append(float(l[-2]))
                # begin vector array
            if len(l) == 6 and l[0] != 'X':
                v.append([float(l[3]),float(l[4]),float(l[5])])
            if len(l)==0 and len(v)>0:
                modes.append(N.array(v))
                v = []
    return N.array(freq), N.array(modes)

def GetVibModesMassScaled(OUTCAR):
    file = VIO_open(OUTCAR,'r')
    print 'VaspIO.GetVibrations: Reading', OUTCAR
    freq = []
    modes = []
    v = []    
    datablock = False
    for line in file:
        if 'Finite differences POTIM=' in line:
            datablock = False # end of data block
        if datablock:
            l = line.split()
            if 'meV' in line:
                # grep frequency
                print line,
                freq.append(float(l[-2]))
                # begin vector array
            if len(l) == 6 and l[0] != 'X':
                v.append([float(l[3]),float(l[4]),float(l[5])])
            if len(l)==0 and len(v)>0:
                modes.append(N.array(v))
                v = []
        if 'Eigenvectors after division by SQRT(mass)' in line:
            datablock = True
    return N.array(freq), N.array(modes)

def ExtractPDOS(filename,outfile,atom_index=[]):
    "Read DOSCAR file and sum over group of atoms (python numbering)"
    print 'VaspIO.ExtractPDOS: Reading',filename
    f = VIO_open(filename,'r')
    # Read number of atoms on first line
    s = f.readline()
    s = s.split()
    atoms = int(s[0])
    print 'Atoms =',atoms
    # skip 4 lines
    for i in range(4):
        f.readline()
    # Read Emin,Emax,pts,eF
    s = f.readline()
    s = s.split()
    Emax = float(s[0])
    Emin = float(s[1])
    pts = int(s[2])
    eF = float(s[3])
    print 'Emin,Emax,pts =',Emin,Emax,pts
    print 'eF = ',eF
    # If atom_index not specified take all:
    if atom_index==[]: 
        atom_index = range(atoms)
    # Loop over atom PDOS
    dat = N.zeros((pts,19),N.float)
    for j in range(atoms):
        for e in range(pts):
            s = f.readline()
            s = s.split()
            # determine spin deg. freedom
            if e==0:
                if len(s)==19:
                    spin = 2
                elif len(s)==10:
                    spin = 1
                elif len(s)==3:
                    # VASP wrote 3-column data...
                    extrablock = 1
                else:
                    extrablock = 0
            for i in range(len(s)):
                s[i] = float(s[i])
            if (j-extrablock) in atom_index:
                dat[e,0] = s[0]-eF
                dat[e,1:1+9*spin] += N.array(s[1:1+9*spin])
                if e==0:
                    print '  adding %i'%(j-extrablock),
            elif e==0:
                print '  skipping %i'%(j-extrablock),
        # skip header line
        f.readline()
    if extrablock==1:
        # Need to read one more block
        j += 1
        for e in range(pts):
            s = f.readline()
            s = s.split()
            # determine spin deg. freedom
            if e==0:
                if len(s)==19:
                    spin = 2
                elif len(s)==10:
                    spin = 1
            for i in range(len(s)):
                s[i] = float(s[i])
            if (j-extrablock) in atom_index:
                dat[e,0] = s[0]-eF
                dat[e,1:1+9*spin] += N.array(s[1:1+9*spin])
                if e==0:
                    print '  adding %i'%(j-extrablock),
            elif e==0:
                print '  skipping %i'%(j-extrablock),
        # skip header line
        f.readline()
        print
    # Make spin=2 negative
    if spin==2:
        sgn = N.ones(1+9*spin)
        for i in range(9):
            sgn[2+2*i] = -1.0
        sgn2 = N.array(pts*[sgn])
        dat = dat*sgn2
    # Write output
    print 'VaspIO.ExtractPDOS: Writing',outfile
    fout = open(outfile,'w')
    for i in range(pts):
        s = ''
        for j in range(1+9*spin):
            s += '%.5e '%dat[i,j]
        fout.write(s+'\n')
    fout.close()
