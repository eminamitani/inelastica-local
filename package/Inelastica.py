print "SVN $Id$"

import NEGF
import SiestaIO as SIO
import MakeGeom as MG
import MiscMath as MM
import WriteNetCDF as NCDF
import numpy as N
import numpy.linalg as LA
import Scientific.IO.NetCDF as NC
import sys
import PhysicalConstants as PC
import time
import ValueCheck as VC

########################################################
##################### Main routine #####################
########################################################
def main(options):
    options.XV = '%s/%s.XV'%(options.head,options.systemlabel)
    options.geom = MG.Geom(options.XV)
    # Set up electrodes and device Greens function
    elecL = NEGF.ElectrodeSelfEnergy(options.fnL,options.NA1L,options.NA2L,options.voltage/2.)
    elecL.scaling = options.scaleSigL
    elecR = NEGF.ElectrodeSelfEnergy(options.fnR,options.NA1R,options.NA2R,-options.voltage/2.)
    elecR.scaling = options.scaleSigR
    # Work with GFs etc at two different energies: p=Ef+hw/2 and m=Ef-hw/2
    GFp = NEGF.GF(options.TSHS,elecL,elecR,Bulk=options.UseBulk,DeviceAtoms=options.DeviceAtoms)
    # Prepare lists for various trace factors
    #GF.dGnout = []
    #GF.dGnin = []
    GFp.P1T = []     # M.A.M.A (total e-h damping)
    GFp.P2T = []     # M.AL.M.AR (emission)
    GFp.ehDampL = [] # M.AL.M.AL (L e-h damping)
    GFp.ehDampR = [] # M.AR.M.AR (R e-h damping)
    GFp.nHT = []     # non-Hilbert/Isym factor
    GFp.nHTin = []
    GFp.nHTel = []
    GFp.HT = []      # Hilbert/Iasym factor
    GFm = NEGF.GF(options.TSHS,elecL,elecR,Bulk=options.UseBulk,DeviceAtoms=options.DeviceAtoms)
    GFm.P1T = []     # M.A.M.A (total e-h damping)
    GFm.P2T = []     # M.AL.M.AR (emission)
    GFm.ehDampL = [] # M.AL.M.AL (L e-h damping)
    GFm.ehDampR = [] # M.AR.M.AR (R e-h damping)
    GFm.nHT = []     # non-Hilbert/Isym factor
    GFm.nHTin = []
    GFm.nHTel = []
    GFm.HT = []      # Hilbert/Iasym factor
    # Calculate transmission at Fermi level
    GFp.calcGF(options.energy+options.eta*1.0j,options.kPoint[0:2],ispin=options.iSpin,etaLead=options.etaLead,useSigNCfiles=options.signc)
    basis = SIO.BuildBasis(options.XV,options.DeviceAtoms[0],options.DeviceAtoms[1],GFp.HS.lasto)
    GFp.TeF = GFp.calcT(options.numchan)[0]
    GFm.TeF = GFp.TeF
    # Read phonons
    NCfile = NC.NetCDFFile(options.PhononNetCDF,'r')
    print 'Inelastica: Reading ',options.PhononNetCDF
    hw = N.array(NCfile.variables['hw'][:])
    # Check consistency of PHrun vs TSrun inputs
    IntegrityCheck(options,GFp,basis,NCfile)   
    # Calculate trace factors one mode at a time
    print 'Inelastica: LOEscale =',options.LOEscale
    if options.LOEscale==0.0:
        # LOEscale=0.0 => Original LOE-WBA method
        GFp.calcGF(options.energy+options.eta*1.0j,options.kPoint[0:2],ispin=options.iSpin,etaLead=options.etaLead,useSigNCfiles=options.signc)
        GFm.calcGF(options.energy+options.eta*1.0j,options.kPoint[0:2],ispin=options.iSpin,etaLead=options.etaLead,useSigNCfiles=options.signc)
        for ihw in range(len(hw)):
            calcTraces(options,GFp,GFm,basis,NCfile,ihw)
            calcTraces(options,GFm,GFp,basis,NCfile,ihw)
    else:
        # LOEscale=1.0 => Generalized LOE, see arXiv:1312.7625
        for ihw in range(len(hw)):
            GFp.calcGF(options.energy+hw[ihw]*options.LOEscale/2+options.eta*1.0j,options.kPoint[0:2],ispin=options.iSpin,etaLead=options.etaLead,useSigNCfiles=options.signc)
            GFm.calcGF(options.energy-hw[ihw]*options.LOEscale/2+options.eta*1.0j,options.kPoint[0:2],ispin=options.iSpin,etaLead=options.etaLead,useSigNCfiles=options.signc)
            calcTraces(options,GFp,GFm,basis,NCfile,ihw)
            calcTraces(options,GFm,GFp,basis,NCfile,ihw)
    # Multiply traces with voltage-dependent functions
    calcIETS(options,GFp,GFm,basis,hw)
    NCfile.close()


########################################################
def IntegrityCheck(options,GF,basis,NCfile):
    # Perform consistency checks for device region in 
    # PH and TS calculations by comparing coordinates
    # and atom numbers
    PH_dev = N.array(NCfile.variables['DeviceAtoms'][:])
    PH_xyz = N.array(NCfile.variables['GeometryXYZ'][:])
    PH_anr = N.array(NCfile.variables['AtomNumbers'][:])
    TS_dev = range(options.DeviceAtoms[0],options.DeviceAtoms[1]+1)
    TS_anr = options.geom.anr
    TS_xyz = options.geom.xyz
    print '\nInelastica.IntegrityCheck:'
    print 'A = %s'%options.PhononNetCDF
    print 'B = %s'%options.XV
    print ' idxA    xA       yA       zA   anrA   ',
    print ' idxB    xB       yB       zB   anrB'
    for i in range(max(len(PH_dev),len(TS_dev))):
        # Geom A
        if PH_dev[0]+i in PH_dev:
            s = ('%i'%(PH_dev[0]+i)).rjust(5)
            for j in range(3):
                s += ('%.4f'%(PH_xyz[PH_dev[0]-1+i,j])).rjust(9)
            s += ('%i'%PH_anr[PH_dev[0]-1+i]).rjust(4)
        else:
            s = ('---').center(36)
        s += '  vs'
        # Geom B
        if options.DeviceAtoms[0]+i in TS_dev:
            s += ('%i'%(options.DeviceAtoms[0]+i)).rjust(5)
            for j in range(3):
                s += ('%.4f'%(TS_xyz[options.DeviceAtoms[0]-1+i,j])).rjust(9)
            s += ('%i'%TS_anr[options.DeviceAtoms[0]-1+i]).rjust(4)
        else:
            s += ('---').center(36)
        print s
    # - check 1: Matrix sizes
    PH_H0 = N.array(NCfile.variables['H0'][:])
    if N.shape(PH_H0[0])==N.shape(GF.Gr):
        print '... Check 1 passed: Device orb. space matches'
        check1 = True
    else:
        print '... Check 1 failed: Device orb. space do not match!!!'
        check1 = False
    # - check 2&3: Geometry and atom number
    dist_xyz = 0.0
    dist_anr = 0.0
    for i in range(len(PH_dev)):
        # Geometric distance between atoms
        if i==0:
            # Allow for a global offset of coordinates R
            R = PH_xyz[PH_dev[0]-1+i]-TS_xyz[options.DeviceAtoms[0]-1+i]
            print 'Global offset R = [%.3f %.3f %.3f]'%(R[0],R[1],R[2])
        d = PH_xyz[PH_dev[0]-1+i]-TS_xyz[options.DeviceAtoms[0]-1+i] - R
        dist_xyz += N.dot(d,d)**.5
        # Difference between atom numbers
        if PH_anr[PH_dev[0]-1+i]<200:
            a = PH_anr[PH_dev[0]-1+i]-TS_anr[options.DeviceAtoms[0]-1+i]
        elif PH_anr[PH_dev[0]-1+i]<1200:
            # Deuterated atom in PH calculation
            a = (PH_anr[PH_dev[0]-1+i]-1000)-TS_anr[options.DeviceAtoms[0]-1+i]
        elif PH_anr[PH_dev[0]-1+i]<2200:
            # "Special" species with a mass defined as anr>2000
            a = (PH_anr[PH_dev[0]-1+i]-2000)-TS_anr[options.DeviceAtoms[0]-1+i]
        dist_anr += abs(a)
    if dist_xyz<1e-3:
        print '... Check 2 passed: Atomic coordinates consistent'
        check2 = True
    elif dist_xyz<0.1:
        print '... Check 2 WARNING: Atomic coordinates deviate by %.3f Ang!!!'%dist_xyz
        check2 = True
    else:
        print '... Check 2 failed: Atomic coordinates deviate by %.3f Ang!!!'%dist_xyz
        check2 = False
    if dist_anr<1e-3:
        print '... Check 3 passed: Atomic numbers consistent'
        check3 = True
    else:
        print '... Check 3 failed: Atomic numbers inconsistent!!!'
        check3 = False
    if (not check1) or (not check2) or (not check3):
        sys.exit('Inelastica: Error - inconsistency detected for device region.\n')

def calcTraces(options,GF1,GF2,basis,NCfile,ihw):
    # Calculate various traces over the electronic structure
    # Electron-phonon couplings
    M = N.array(NCfile.variables['He_ph'][ihw,options.iSpin,:,:],N.complex)
    try:
        M += 1.j*N.array(NCfile.variables['ImHe_ph'][ihw,options.iSpin,:,:],N.complex)
    except:
        print 'Warning: Variable ImHe_ph not found'
    # Calculation of intermediate quantity
    MARGLGM = MM.mm(M,GF1.ARGLG,M)
    MARGLGM2 = MM.mm(M,GF2.ARGLG,M)
    # LOE expressions in compact form
    t1 = MM.mm(MARGLGM,GF2.AR)
    t2 = MM.mm(MARGLGM2,GF1.AL)
    K23 = N.trace(t1+t2).imag
    K4 = N.trace(MM.mm(M,GF1.ALT,M,GF2.AR))
    aK23 = 2*N.trace(t1-t2).real # asymmetric part
    # Non-Hilbert term defined here with a minus sign
    GF1.nHTin.append(checkImPart(K4))
    GF1.nHTel.append(checkImPart(K23))
    GF1.nHT.append(checkImPart(K23+K4))
    GF1.HT.append(checkImPart(aK23))
    # Power, damping and current rates
    GF1.P1T.append(checkImPart(N.trace(MM.mm(M,GF1.A,M,GF2.A))))
    GF1.P2T.append(checkImPart(N.trace(MM.mm(M,GF1.AL,M,GF2.AR))))
    GF1.ehDampL.append(checkImPart(N.trace(MM.mm(M,GF1.AL,M,GF2.AL))))
    GF1.ehDampR.append(checkImPart(N.trace(MM.mm(M,GF1.AR,M,GF2.AR))))
    # Remains from older version (see before rev. 219):
    #GF.dGnout.append(EC.calcCurrent(options,basis,GF.HNO,mm(Us,-0.5j*(tmp1-dagger(tmp1)),Us)))
    #GF.dGnin.append(EC.calcCurrent(options,basis,GF.HNO,mm(Us,mm(G,MA1M,Gd)-0.5j*(tmp2-dagger(tmp2)),Us)))
    # NB: TF Should one use GF.HNO (nonorthogonal) or GF.H (orthogonalized) above?

def calcIETS(options,GFp,GFm,basis,hw):
    # Calculate product of electronic traces and voltage functions
    print 'Inelastica.calcIETS: nHTp =',N.array(GFp.nHT)*PC.unitConv # OK
    print 'Inelastica.calcIETS: nHTm =',N.array(GFm.nHT)*PC.unitConv # OK
    print 'Inelastica.calcIETS: HTp  =',N.array(GFp.HT) # OK
    print 'Inelastica.calcIETS: HTm  =',N.array(GFm.HT) # OK
    
    # Set up grid and Hilbert term
    kT = options.Temp/11604.0 # (eV)

    # Generate grid for numerical integration of Hilbert term    
    max_hw=max(hw)
    max_win=max(-options.minBias,max_hw)+20*kT+4*options.Vrms
    min_win=min(-options.maxBias,-max_hw)-20*kT-4*options.Vrms
    pts=int(N.floor((max_win-min_win)/kT*3))
    Egrid=N.linspace(min_win,max_win,pts)
    print "Inelastica.calcIETS: Hilbert integration grid : %i pts [%f,%f]" % (pts,min(Egrid),max(Egrid))

    NN = options.biasPoints
    print 'Inelastica.calcIETS: Biaspoints =',NN

    # Add some points for the Lock in broadening
    approxdV=(options.maxBias-options.minBias)/(NN-1)
    NN+=int(((8*options.Vrms)/approxdV)+.5)    
    Vl=N.linspace(options.minBias-4*options.Vrms,options.maxBias+4*options.Vrms,NN)

    # Vector implementation on Vgrid:
    wp = (1+N.sign(Vl))/2. # weights for positive V 
    wm = (1-N.sign(Vl))/2. # weights for negative V
    
    # Mode occupation and power dissipation
    Pow = N.zeros((len(hw),NN),N.float) # (modes,Vgrid)
    nPh = N.zeros((len(hw),NN),N.float)
    t0 = N.clip(Vl/kT,-700,700)
    cosh0 = N.cosh(t0) # Vgrid
    sinh0 = N.sinh(t0)
    for i in range(len(hw)):
        P1T = wm*GFm.P1T[i]+wp*GFp.P1T[i]
        P2T = wm*GFm.P2T[i]+wp*GFp.P2T[i]
        # Bose distribution
        nB = 1/(N.exp(N.clip(hw[i]/kT,-300,300))-1) # number
        t1 = N.clip(hw[i]/(2*kT),-700,700) # number
        coth1 = N.cosh(t1)/N.sinh(t1)
        # Emission rate and e-h damping
        damp = P1T*hw[i]/N.pi # Vgrid
        emis = P2T*(hw[i]*(cosh0-1)*coth1-Vl*sinh0)/(N.cosh(2*t1)-cosh0)/N.pi
        # Determine mode occupation
        if options.PhHeating:
            nPh[i,:] = emis/(hw[i]*P1T/N.pi+options.PhExtDamp)+nB
        else:
            nPh[i,:] = nB
        # Mode-resolved power dissipation
        Pow[i,:] = hw[i]*((nB-nPh[i])*damp+emis)

    # Current: non-Hilbert part (InH)
    InH = N.zeros((NN,),N.float) # Vgrid
    for i in range(len(hw)):
        nHT = wm*GFm.nHT[i]+wp*GFp.nHT[i] # Vgrid
        t1 = hw[i]/(2*kT) # number 
        t1 = N.clip(t1,-700,700)
        coth1 = N.cosh(t1)/N.sinh(t1)
        t2 = (hw[i]+Vl)/(2*kT) # Vgrid
        t2 = N.clip(t2,-700,700)
        coth2 = N.cosh(t2)/N.sinh(t2)
        t3 = (hw[i]-Vl)/(2*kT) # Vgrid
        t3 = N.clip(t3,-700,700)
        coth3 = N.cosh(t3)/N.sinh(t3) # Vgrid
        # Isym function
        Isym = 0.5*(hw[i]+Vl)*(coth1-coth2) # Vgrid
        Isym -= 0.5*(hw[i]-Vl)*(coth1-coth3)
        # non-Hilbert part
        InH += (Isym+Vl*nPh[i])*nHT # Vgrid

    # Current: Add Landauer part, GFm.TeF = GFp.TeF
    InH += GFp.TeF*Vl # Vgrid

    # Current: Hilbert part
    IH = N.zeros((NN,),N.float)
    # Prepare box/window function on array
    Vl2 = N.outer(Vl,N.ones(Egrid.shape)) 
    Egrid2 = N.outer(N.ones(Vl.shape),Egrid)
    # Box/window function nF(E-Vl2)-nF(E-0):
    kasse = MM.box(0,-Vl2,Egrid2,kT) # (Vgrid,Egrid)
    ker = None
    for i in range(len(hw)):
        # Box/window function nF(E-hw)-nF(E+hw)
        tmp = MM.box(-hw[i],hw[i],Egrid,kT)
        hilb, ker = MM.Hilbert(tmp,ker) # Egrid
        # Calculate Iasym for each bias point
        for j in range(len(Vl)):
            Iasym = MM.trapez(Egrid,kasse[j]*hilb,equidistant=True)/2
            if Vl[j]>0:
                IH[j] += GFp.HT[i]*Iasym
            else:
                IH[j] += GFm.HT[i]*Iasym

    # Get the right units for gamma_eh, gamma_heat
    gamma_eh_p=N.zeros((len(hw),),N.float)
    gamma_eh_m=N.zeros((len(hw),),N.float)
    gamma_heat_p=N.zeros((len(hw),),N.float)
    gamma_heat_m=N.zeros((len(hw),),N.float)
    for iOmega in range(len(hw)):
        # Units [Phonons per Second per dN where dN is number extra phonons]
        gamma_eh_p[iOmega]=GFp.P1T[iOmega]*hw[iOmega]*PC.unitConv
        gamma_eh_m[iOmega]=GFm.P1T[iOmega]*hw[iOmega]*PC.unitConv
        # Units [Phonons per second per eV [eV-ihw]
        gamma_heat_p[iOmega]=GFp.P2T[iOmega]*PC.unitConv
        gamma_heat_m[iOmega]=GFm.P2T[iOmega]*PC.unitConv

    print 'Inelastica.calcIETS: gamma_eh_p =',gamma_eh_p # OK
    print 'Inelastica.calcIETS: gamma_eh_m =',gamma_eh_m # OK
    print 'Inelastica.calcIETS: gamma_heat_p =',gamma_heat_p # OK
    print 'Inelastica.calcIETS: gamma_heat_m =',gamma_heat_m # OK

    V, I, dI, ddI, BdI, BddI, NPow, NnPh = Broaden(options,Vl,InH+IH,Pow,nPh)

    # Total power and phonons
    NPowtot = N.sum(NPow,axis=0) # sum over modes
    NnPhtot = N.sum(NnPh,axis=0) # sum over modes

    print 'Inelastica.calcIETS: V[:5]        =',V[:5] # OK
    print 'Inelastica.calcIETS: V[-5:][::-1] =',V[-5:][::-1] # OK
    print 'Inelastica.calcIETS: I[:5]        =',I[:5] # OK
    print 'Inelastica.calcIETS: I[-5:][::-1] =',I[-5:][::-1] # OK
    print 'Inelastica.calcIETS: BdI[:5]        =',BdI[:5] # OK
    print 'Inelastica.calcIETS: BdI[-5:][::-1] =',BdI[-5:][::-1] # OK
    print 'Inelastica.calcIETS: BddI[:5]        =',BddI[:5] # OK
    print 'Inelastica.calcIETS: BddI[-5:][::-1] =',BddI[-5:][::-1] # OK

    datafile = '%s/%s.IN'%(options.DestDir,options.systemlabel)
    # ascii
    writeLOEData2Datafile(datafile+'p',hw,GFp.TeF,GFp.nHT,GFp.HT)
    writeLOEData2Datafile(datafile+'m',hw,GFm.TeF,GFm.nHT,GFm.HT)
    # netcdf
    initncfile(datafile+'p',hw)
    writeLOE2ncfile(datafile+'p',hw,GFp.nHT,GFp.HT,V,I,NnPhtot,N.transpose(NnPh),\
                    dI,ddI,BdI,BddI,gamma_eh_p,gamma_heat_p,options)
    initncfile(datafile+'m',hw)
    writeLOE2ncfile(datafile+'m',hw,GFm.nHT,GFm.HT,V,I,NnPhtot,N.transpose(NnPh),\
                    dI,ddI,BdI,BddI,gamma_eh_p,gamma_heat_p,options)

    
########################################################
def checkImPart(x):
    VC.Check("zero-imaginary-part",abs(x.imag),
             "Imaginary part too large.")
    return x.real   

########################################################
def writeFGRrates():
    # This does not work at the moment....
    NCfile = NC.NetCDFFile(options.PhononNetCDF,'r')
    print 'Reading ',options.PhononNetCDF

    options.iChan, options.iSide = 0, 2
    outFile = file('%s/%s.IN.FGR'%(options.DestDir,options.systemlabel,'w'))
    outFile.write('Total transmission [in units of (1/s/eV)] : %e\n' % (PC.unitConv*GF.totTrans.real,))

    tmp=N.sort(abs(N.array(GF.nHT[:])))
    SelectionMin=tmp[-options.NumPhCurr]        
    
    for ihw in range(len(GF.hw)):
        SIO.printDone(ihw,len(GF.hw),'Golden Rate') 
        M = N.array(NCfile.variables['He_ph'][ihw,options.iSpin,:,:],N.complex) + 1.j*N.array(NCfile.variables['ImHe_ph'][ihw,options.iSpin,:,:],N.complex)
        rate=N.zeros((len(GF.ECleft),len(GF.ECright)),N.float)
        totrate=0.0
        inter,intra = 0.0, 0.0 # splitting total rate in two
        for iL in range(len(GF.ECleft)):
            for iR in range(len(GF.ECright)):
                tmp=N.dot(N.conjugate(GF.ECleft[iL]),mm(M,GF.ECright[iR]))
                rate[iL,iR]=(2*N.pi)**2*abs(tmp)**2
                totrate+=rate[iL,iR]
                if iL==iR: intra += rate[iL,iR]
                else: inter += rate[iL,iR]

        if abs(GF.nHT[ihw])>=SelectionMin:
            options.iChan = ihw
            currOut, currIn = IETS.dGnout[ihw], IETS.dGnin[ihw]
            options.iSide = 3
            writeCurrent(currIn)
            options.iSide = 4
            writeCurrent(currOut)
            
        outFile.write('\nPhonon mode %i : %f eV [Rates in units of (1/s/eV)]\n' % (ihw,IETS.hw[ihw]))
        outFile.write('eh-damp : %e (1/s) , heating %e (1/(sV)))\n' % (IETS.P1T[ihw]*PC.unitConv*IETS.hw[ihw],IETS.P2T[ihw]*PC.unitConv))
        outFile.write('eh-damp 1, 2 (MALMAL, MARMAR): %e (1/s) , %e (1/(s)))\n' % (IETS.ehDampL[ihw]*PC.unitConv*IETS.hw[ihw],IETS.ehDampR[ihw]*PC.unitConv*IETS.hw[ihw]))
        outFile.write('SymI : %e (1/(sV)) , AsymI %e (?))\n' % (IETS.nHT[ihw]*PC.unitConv,IETS.HT[ihw]*PC.unitConv))
        outFile.write('Elast : %e (1/(sV)) , Inelast %e (1/(sV)))\n' % (IETS.nHTel[ihw]*PC.unitConv,IETS.nHTin[ihw]*PC.unitConv))
        outFile.write('down=left EC, right=right EC\n')
        if IETS.P2T[ihw]>0.0:
            if abs(totrate/(IETS.P2T[ihw])-1)<0.05:
                outFile.write('Sum/Tr[MALMAR] , Tr: %1.3f  %e\n'%(totrate/(IETS.P2T[ihw]),PC.unitConv*IETS.P2T[ihw]))
            else:
                outFile.write('WARNING: !!!! Sum/Tr[MALMAR] , Tr: %2.2e  %e\n'%(totrate/(IETS.P2T[ihw]),PC.unitConv*IETS.P2T[ihw]))
        else:
            outFile.write(' Tr:  %e\n'%(PC.unitConv*IETS.P2T[ihw]))
        inter = inter/IETS.P2T[ihw]
        intra = intra/IETS.P2T[ihw]
        outFile.write('Interchannel ratio: Sum(inter)/Tr[MALMAR]      = %.4f \n'%inter)
        outFile.write('Intrachannel ratio: Sum(intra)/Tr[MALMAR]      = %.4f \n'%intra)
        outFile.write('Inter+intra ratio: Sum(inter+intra)/Tr[MALMAR] = %.4f \n'%(inter+intra))
        for iL in range(len(IETS.ECleft)):
            for iR in range(len(IETS.ECright)):
                outFile.write('%e ' % (PC.unitConv*rate[iL,iR],))
            outFile.write('\n')
        outFile.close()
        NCfile.close()
                        


################################################################
# Broadening due to Vrms
################################################################

def Broaden(options,VV,II,Pow,nPh):
    """
    Broadening corresponding to Lock in measurements for the
    conductance and IETS spectra. Also resample II, Pow, and nPh
    to match a common voltage list
    """

    II=II.copy()
    II=II.real
    
    # First derivative dI and bias list dV
    dI=(II[1:len(II)]-II[:-1])/(VV[1]-VV[0])
    dV=(VV[1:len(VV)]+VV[:-1])/2
    # Second derivative and bias ddV
    ddI=(dI[1:len(dI)]-dI[:-1])/(VV[1]-VV[0])
    ddV=(dV[1:len(dV)]+dV[:-1])/2

    # Modulation amplitude
    VA=N.sqrt(2.0)*options.Vrms 

    # New bias ranges for broadening
    tmp=int(N.floor(VA/(dV[1]-dV[0]))+1)
    BdV=dV[tmp:-tmp]
    BddV=ddV[tmp:-tmp]

    # Initiate derivatives
    BdI=0*BdV
    BddI=0*BddV
    
    # Calculate first derivative with Vrms broadening
    for iV, V in enumerate(BdV):
        SIO.printDone(iV,len(BdV),'Inelastica.Broaden: First-derivative Vrms broadening')
        wt=(N.array(range(200))/200.0-0.5)*N.pi
        VL=V+VA*N.sin(wt)
        dIL=MM.interpolate(VL,dV,dI)
        BdI[iV]=2/N.pi*N.sum(dIL*(N.cos(wt)**2))*(wt[1]-wt[0])

    # Calculate second derivative with Vrms broadening    
    for iV, V in enumerate(BddV):
        SIO.printDone(iV,len(BddV),'Inelastica.Broaden: Second-derivative Vrms broadening')
        wt=(N.array(range(200))/200.0-0.5)*N.pi
        VL=V+VA*N.sin(wt)
        ddIL=MM.interpolate(VL,ddV,ddI)
        BddI[iV]=8.0/3.0/N.pi*N.sum(ddIL*(N.cos(wt)**4))*(wt[1]-wt[0])

    # Reduce to one voltage grid
    NN=options.biasPoints
    V = N.linspace(options.minBias,options.maxBias,NN)

    NI=MM.interpolate(V,VV,II)
    NdI=MM.interpolate(V,dV,dI)
    NddI=MM.interpolate(V,ddV,ddI)
    NBdI=MM.interpolate(V,BdV,BdI)
    NBddI=MM.interpolate(V,BddV,BddI)
    NPow=N.zeros((len(Pow),len(V)),N.float)
    NnPh=N.zeros((len(nPh),len(V)),N.float)
    for ii in range(len(nPh)):
        NPow[ii]=MM.interpolate(V,VV,Pow[ii])
        NnPh[ii]=MM.interpolate(V,VV,nPh[ii])
    
    return V, NI ,NdI, NddI, NBdI, NBddI, NPow, NnPh

################################################################
# Output to NetCDF file
################################################################

def initncfile(filename,hw):
    'Initiate netCDF file'
    print 'Inelastica: Initializing nc-file'
    ncfile = NC.NetCDFFile(filename+'.nc','w','Created '+time.ctime(time.time()))
    ncfile.title = 'Inelastica Output'
    ncfile.version = 1
    ncfile.createDimension('Nph',len(hw))
    nchw = ncfile.createVariable('hw','d',('Nph',))
    nchw[:] = N.array(hw)
    nchw.units = 'eV'
    ncfile.close()
    
def writeLOE2ncfile(filename,hw,nHT,HT,V,I,nPhtot,nPh,\
                        dI,ddI,BdI,BddI,gamma_eh,gamma_heat,options):
    'Write LOE data to netCDF file'
    print 'Inelastica: Write LOE data to nc-file'
    ncfile = NC.NetCDFFile(filename+'.nc','a')
    ncfile.createDimension('LOE_V',len(V))
    tmp=ncfile.createVariable('LOE_V','d',('LOE_V',))
    tmp[:]=N.array(V)
    tmp.units='V'
    tmp=ncfile.createVariable('LOE_IETS','d',('LOE_V',))
    tmpn=BddI/BdI
    tmp[:]=N.array(tmpn.real)
    tmp.units='Broadened ddI/dI [1/V]'
    tmp=ncfile.createVariable('LOE_dI','d',('LOE_V',))
    tmp[:]=N.array(dI.real)
    tmp.units='dI LOE, G0'
    tmp=ncfile.createVariable('LOE_ddI','d',('LOE_V',))
    tmp[:]=N.array(ddI.real)
    tmp.units='ddI LOE, G0/V'
    tmp=ncfile.createVariable('LOE_BdI','d',('LOE_V',))
    tmp[:]=N.array(BdI.real)
    tmp.units='Broadened dI LOE, G0'
    tmp=ncfile.createVariable('LOE_BddI','d',('LOE_V',))
    tmp[:]=N.array(BddI.real)
    tmp.units='Broadened ddI LOE, G0/V'
    tmp=ncfile.createVariable('LOE_I','d',('LOE_V',))
    tmp[:]=N.array(I.real)
    tmp.units='G0 V'
    tmp=ncfile.createVariable('LOE_tot_nPh','d',('LOE_V',))
    tmp[:]=N.array(nPhtot.real)
    tmp.units='Total number of phonons '
    tmp=ncfile.createVariable('LOE_nPh','d',('LOE_V','Nph'))
    tmp[:]=N.array(nPh.real)
    tmp.units='Number of phonons'
    tmp=ncfile.createVariable('LOE_gamma_eh','d',('Nph',))
    tmp[:]=N.array(gamma_eh)
    tmp.units='e-h damping [*deltaN=1/Second]'
    tmp=ncfile.createVariable('LOE_gamma_heat','d',('Nph',))
    tmp[:]=N.array(gamma_heat)
    # Symmetric part
    tmp.units='Phonon heating [*(bias-hw) (eV) = 1/Second]'
    ncTotR = ncfile.createVariable('LOE_ISymTr','d',('Nph',))
    ncTotR[:] = N.array(nHT)*PC.unitConv
    ncTotR.units = 'Trace giving Symmetric current contribution (same units as eigenchannels [1/s/eV])'
    ncTotR2 = ncfile.createVariable('LOE_ISymTr2','d',('Nph',))
    ncTotR2[:] = N.array(nHT)
    ncTotR2.units = 'Trace giving Symmetric current contribution (same units as asymmetric contrib.)'
    # Asymmetric part
    ncTotL = ncfile.createVariable('LOE_IAsymTr','d',('Nph',))
    ncTotL[:] = N.array(HT)
    ncTotL.units = 'Trace giving Asymmetric current contribution'
    # Write energy reference where Greens functions are evaluated
    ncfile.createDimension('number',1)
    tmp=ncfile.createVariable('EnergyRef','d',('number',))
    tmp[:]=N.array(options.energy)
    # Write LOEscale
    tmp=ncfile.createVariable('LOEscale','d',('number',))
    tmp[:]=N.array(options.LOEscale)
    # Write k-point
    ncfile.createDimension('vector',3)
    tmp=ncfile.createVariable('kpoint','d',('vector',))
    tmp[:]=N.array(options.kPoint)
    ncfile.close()

    
def writeLOEData2Datafile(file,hw,T,nHT,HT):
    f = open(file,'a')
    f.write("## Almost First Order Born Approximation (kbT=0)\n")
    f.write("## hw(eV)      Trans        non-H-term (e/pi/hbar)   H-term\n")
    for ii in range(len(hw)):
        f.write("## %e %e %e %e\n" % (hw[ii],T,nHT[ii],HT[ii]))
    f.write("\n")
    f.close()

